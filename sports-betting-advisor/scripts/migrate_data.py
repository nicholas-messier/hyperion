#!/usr/bin/env python3
"""
migrate_data.py -- One-time migration from markdown/JSON to the SQLite database.

Parses:
  - Bet history from data/celtics_postseason_2026.md (the markdown tables)
  - Bankroll ledger entries from the same file
  - Active bets from ~/.config/sports-bets/active_bets.json
  - Bankroll state from ~/.config/sports-bets/bankroll.json

Usage:
    python3 scripts/migrate_data.py          # Migrate everything
    python3 scripts/migrate_data.py --dry-run  # Preview without writing

IMPORTANT: Review output manually after running -- markdown parsing can be fragile.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Add scripts dir to path for db import
sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

# ── Paths ────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
POSTSEASON_MD = DATA_DIR / "celtics_postseason_2026.md"
ACTIVE_BETS_JSON = Path.home() / ".config" / "sports-bets" / "active_bets.json"
BANKROLL_JSON = Path.home() / ".config" / "sports-bets" / "bankroll.json"

# Map of player -> team (from the postseason doc context)
PLAYER_TEAMS = {
    "Jayson Tatum": "BOS", "Jaylen Brown": "BOS",
    "Derrick White": "BOS", "Jrue Holiday": "BOS",
    "Al Horford": "BOS", "Kristaps Porzingis": "BOS",
    "Tyrese Maxey": "PHI", "Nikola Jokic": "DEN",
    "Jalen Brunson": "NYK", "Victor Wembanyama": "SAS",
    "Shai Gilgeous-Alexander": "OKC", "Anthony Edwards": "MIN",
    "Donovan Mitchell": "CLE", "Paolo Banchero": "ORL",
    "Cade Cunningham": "DET", "LeBron James": "LAL",
    "Alperen Sengun": "HOU",
}


def parse_bet_history(md_text):
    """Parse the Bet History table from the markdown.

    Expected format:
    | Date | Bet | Wager | Result | Payout | Net |
    """
    bets = []
    in_history = False

    for line in md_text.splitlines():
        if "## Bet History" in line:
            in_history = True
            continue
        if in_history and line.startswith("##"):
            break
        if not in_history:
            continue

        # Skip header / separator rows
        if not line.startswith("|") or "---" in line or "Date" in line:
            continue

        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 6:
            continue

        date_str, bet_desc, wager_str, result, payout_str, net_str = cols[:6]

        # Parse wager
        wager_match = re.search(r"\$(\d+\.?\d*)", wager_str)
        wager = float(wager_match.group(1)) if wager_match else 0

        # Parse payout
        payout_match = re.search(r"\$(\d+\.?\d*)", payout_str)
        payout = float(payout_match.group(1)) if payout_match else 0

        # Parse result
        if result.strip() == "W":
            res = "W"
        elif result.strip() == "L":
            res = "L"
        else:
            continue

        # Parse bet description to extract player, stat, target
        player = ""
        stat = ""
        target = 0
        is_parlay = "Parlay" in bet_desc or "parlay" in bet_desc

        if is_parlay:
            # e.g. "Parlay: Tatum REB + Brown PTS" or "Parlay: Jokic REB + Brunson PTS"
            bets.append({
                "type": "parlay",
                "description": bet_desc,
                "date": date_str,
                "wager": wager,
                "result": res,
                "payout": payout,
            })
            continue

        # Straight bet: "Tatum 10+ REB" or "Brown 25+ PTS" or "Jokic Over 10.5 REB (-446)"
        # Try "Player N+ STAT" format
        m = re.match(r"(.+?)\s+(\d+)\+\s+(\w+)", bet_desc)
        if m:
            player_short = m.group(1).strip()
            target = int(m.group(2))
            stat = m.group(3).upper()
        else:
            # Try "Player Over N.N STAT" format
            m = re.match(r"(.+?)\s+Over\s+(\d+\.?\d*)\s+(\w+)", bet_desc)
            if m:
                player_short = m.group(1).strip()
                target = int(float(m.group(2)) + 0.5)  # round up for over
                stat = m.group(3).upper()
            else:
                player_short = bet_desc
                stat = ""
                target = 0

        # Resolve full player name from short name
        for full_name in PLAYER_TEAMS:
            last_name = full_name.split()[-1]
            if last_name in player_short:
                player = full_name
                break
        if not player:
            player = player_short

        # Extract odds if present
        odds = 0
        odds_match = re.search(r"\(([+-]\d+)\)", bet_desc)
        if odds_match:
            odds = int(odds_match.group(1))

        team = PLAYER_TEAMS.get(player, "")

        bets.append({
            "type": "straight",
            "player": player,
            "team": team,
            "stat": stat,
            "target": target,
            "wager": wager,
            "result": res,
            "payout": payout,
            "odds": odds,
            "date": date_str,
        })

    return bets


def parse_bankroll_ledger(md_text):
    """Parse the Bankroll Tracker table from the markdown.

    Expected format:
    | Date | Action | Amount | Balance |
    """
    entries = []
    in_tracker = False

    for line in md_text.splitlines():
        if "## Bankroll Tracker" in line:
            in_tracker = True
            continue
        if in_tracker and line.startswith("##"):
            break
        if not in_tracker:
            continue

        if not line.startswith("|") or "---" in line or "Date" in line:
            continue

        cols = [c.strip() for c in line.split("|")[1:-1]]
        if len(cols) < 4:
            continue

        date_str, action_desc, amount_str, balance_str = cols[:4]

        # Parse balance
        bal_match = re.search(r"\$(\d+\.?\d*)", balance_str)
        balance = float(bal_match.group(1)) if bal_match else 0

        # Parse amount
        amt_match = re.search(r"[+-]?\$(\d+\.?\d*)", amount_str)
        if amt_match:
            amount = float(amt_match.group(1))
            if "-" in amount_str:
                amount = -amount
        elif amount_str.strip() == "—" or amount_str.strip() == "":
            amount = balance  # starting bankroll
        else:
            amount = 0

        # Determine action type
        action_lower = action_desc.lower()
        if "starting" in action_lower:
            action = "deposit"
        elif "deposit" in action_lower:
            action = "deposit"
        elif "win" in action_lower:
            action = "bet_settled"
        elif "loss" in action_lower:
            action = "bet_settled"
        elif "bet" in action_lower or "parlay" in action_lower:
            action = "bet_placed"
        else:
            action = "adjustment"

        entries.append({
            "date": date_str,
            "action": action,
            "amount": amount,
            "balance": balance,
            "notes": action_desc,
        })

    return entries


def parse_active_bets_json():
    """Read active bets from the JSON file."""
    if not ACTIVE_BETS_JSON.exists():
        return [], []
    data = json.loads(ACTIVE_BETS_JSON.read_text())
    return data.get("bets", []), data.get("parlays", [])


def parse_parlay_legs(description):
    """Extract parlay legs from a bet description.

    e.g. "Parlay: Tatum REB + Brown PTS" -> [("Jayson Tatum", "REB"), ("Jaylen Brown", "PTS")]
    """
    legs = []
    # Remove "Parlay:" prefix and odds suffix
    desc = re.sub(r"^Parlay:\s*", "", description)
    desc = re.sub(r"\s*\([^)]+\)\s*$", "", desc)

    parts = re.split(r"\s*\+\s*", desc)
    for part in parts:
        # "Tatum REB" or "Jokic REB" or "Brunson PTS"
        m = re.match(r"(\w+)\s+(\w+)", part.strip())
        if m:
            short_name = m.group(1)
            stat = m.group(2).upper()
            # Resolve full name
            player = short_name
            for full_name in PLAYER_TEAMS:
                if full_name.split()[-1] == short_name:
                    player = full_name
                    break
            legs.append({"player": player, "stat": stat})
    return legs


def migrate(dry_run=False):
    """Run the full migration."""
    print("=" * 60)
    print("  Sports Betting Advisor — Data Migration")
    print("=" * 60)

    if dry_run:
        print("  MODE: DRY RUN (no changes will be made)\n")
    else:
        print()

    # Initialize the database
    if not dry_run:
        db.init_db()

    # ── 1. Parse markdown ────────────────────────────────────
    if not POSTSEASON_MD.exists():
        print(f"  WARNING: {POSTSEASON_MD} not found. Skipping markdown migration.")
        md_text = ""
    else:
        md_text = POSTSEASON_MD.read_text()

    # Parse bankroll ledger
    ledger_entries = parse_bankroll_ledger(md_text) if md_text else []
    print(f"  Bankroll ledger entries parsed: {len(ledger_entries)}")

    # Parse bet history
    bet_history = parse_bet_history(md_text) if md_text else []
    straight_bets = [b for b in bet_history if b["type"] == "straight"]
    parlay_bets = [b for b in bet_history if b["type"] == "parlay"]
    print(f"  Bet history parsed: {len(straight_bets)} straight, {len(parlay_bets)} parlays")

    # ── 2. Parse active bets JSON ────────────────────────────
    active_bets, active_parlays = parse_active_bets_json()
    print(f"  Active bets from JSON: {len(active_bets)} bets, {len(active_parlays)} parlays")

    # ── 3. Preview ───────────────────────────────────────────
    print(f"\n  {'─' * 50}")
    print("  BANKROLL LEDGER PREVIEW:")
    for entry in ledger_entries[:5]:
        print(f"    {entry['date']:>15} | {entry['action']:<12} | "
              f"${entry['amount']:>8.2f} | Balance: ${entry['balance']:.2f}")
    if len(ledger_entries) > 5:
        print(f"    ... and {len(ledger_entries) - 5} more entries")

    print(f"\n  BET HISTORY PREVIEW:")
    for bet in bet_history[:5]:
        if bet["type"] == "straight":
            print(f"    {bet['date']:>8} | {bet['player']:<20} | "
                  f"{bet['stat']:>3} {bet['target']}+ | "
                  f"${bet['wager']:.2f} | {bet['result']} | ${bet['payout']:.2f}")
        else:
            print(f"    {bet['date']:>8} | PARLAY: {bet['description'][:30]:<30} | "
                  f"${bet['wager']:.2f} | {bet['result']} | ${bet['payout']:.2f}")

    print(f"\n  ACTIVE BETS PREVIEW:")
    for bet in active_bets:
        print(f"    {bet['player']:<20} | {bet.get('team', '?'):>3} | "
              f"{bet['stat']:>3} {bet['target']}+ | ${bet.get('wager', 0):.2f}")
    for parlay in active_parlays:
        legs = ", ".join(parlay.get("legs", []))
        print(f"    PARLAY: {legs} | ${parlay.get('wager', 0):.2f}")

    if dry_run:
        print(f"\n  DRY RUN COMPLETE. No data was written.")
        return

    # ── 4. Write to database ─────────────────────────────────
    print(f"\n  {'─' * 50}")
    print("  WRITING TO DATABASE...")

    # Write bankroll ledger
    for entry in ledger_entries:
        db.update_bankroll.__wrapped__ if hasattr(db.update_bankroll, '__wrapped__') else None
        conn = db._get_conn()
        conn.execute(
            """INSERT INTO bankroll_ledger
               (timestamp, action, amount, balance, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (entry["date"], entry["action"], entry["amount"],
             entry["balance"], entry["notes"]),
        )
    conn = db._get_conn()
    conn.commit()
    print(f"    Bankroll ledger: {len(ledger_entries)} entries written")

    # Write settled bets (history)
    bet_count = 0
    parlay_count = 0

    for bet in straight_bets:
        db.record_bet(
            player=bet["player"],
            stat=bet["stat"],
            target=bet["target"],
            wager=bet["wager"],
            team=bet.get("team", ""),
            odds=bet.get("odds", 0),
            placed_at=bet["date"],
        )
        # Settle it
        conn = db._get_conn()
        last_id = conn.execute("SELECT MAX(id) FROM bets").fetchone()[0]
        conn.execute(
            "UPDATE bets SET result = ?, payout = ?, settled_at = ? WHERE id = ?",
            (bet["result"], bet["payout"], bet["date"], last_id),
        )
        conn.commit()
        bet_count += 1

    for parlay_bet in parlay_bets:
        legs = parse_parlay_legs(parlay_bet["description"])
        if not legs:
            continue

        # Find matching targets from straight bet history
        for leg in legs:
            for sb in straight_bets:
                if sb["player"] == leg["player"] and sb["stat"] == leg["stat"]:
                    leg["target"] = sb["target"]
                    leg["team"] = sb.get("team", "")
                    break
            if "target" not in leg:
                leg["target"] = 0
                leg["team"] = PLAYER_TEAMS.get(leg["player"], "")

        parlay_id = db.record_parlay(
            legs=legs,
            wager=parlay_bet["wager"],
            placed_at=parlay_bet["date"],
        )
        # Settle it
        conn = db._get_conn()
        conn.execute(
            "UPDATE parlays SET result = ?, payout = ?, settled_at = ? WHERE id = ?",
            (parlay_bet["result"], parlay_bet["payout"], parlay_bet["date"], parlay_id),
        )
        conn.execute(
            "UPDATE bets SET result = ?, settled_at = ? WHERE parlay_id = ?",
            (parlay_bet["result"], parlay_bet["date"], parlay_id),
        )
        conn.commit()
        parlay_count += 1

    print(f"    Settled bets: {bet_count} straight, {parlay_count} parlays")

    # Write active bets
    active_count = 0
    active_parlay_count = 0

    # First, create parlays
    parlay_id_map = {}  # JSON parlay name -> DB parlay ID
    for parlay in active_parlays:
        legs_data = []
        for leg_str in parlay.get("legs", []):
            parts = leg_str.split(":")
            if len(parts) == 3:
                p_name, p_stat, p_target = parts
                # Spread / run-line / puck-line targets are floats
                # ('-12.5'); player props are ints. Try int first.
                try:
                    target_val = int(p_target)
                except ValueError:
                    target_val = float(p_target)
                legs_data.append({
                    "player": p_name,
                    "stat": p_stat,
                    "target": target_val,
                    "team": PLAYER_TEAMS.get(p_name, ""),
                })
        if legs_data:
            pid = db.record_parlay(
                legs=legs_data,
                wager=parlay.get("wager", 0),
            )
            parlay_id_map[parlay.get("name", "")] = pid
            active_parlay_count += 1

    # Then, create straight bets (skip parlay legs already created)
    parlay_leg_keys = set()
    for parlay in active_parlays:
        for leg_str in parlay.get("legs", []):
            parlay_leg_keys.add(leg_str)

    for bet in active_bets:
        leg_key = f"{bet['player']}:{bet['stat']}:{int(bet['target'])}"
        if leg_key in parlay_leg_keys and bet.get("wager", 0) == 0:
            continue  # Already created as parlay leg
        if bet.get("wager", 0) > 0:
            db.record_bet(
                player=bet["player"],
                stat=bet["stat"],
                target=bet["target"],
                wager=bet.get("wager", 0),
                team=bet.get("team", ""),
            )
            active_count += 1

    print(f"    Active bets: {active_count} straight, {active_parlay_count} parlays")

    # Sync JSON files
    db.sync_json()
    print(f"\n    JSON files synced (bankroll.json + active_bets.json)")

    # ── 5. Verification ──────────────────────────────────────
    print(f"\n  {'─' * 50}")
    print("  VERIFICATION:")

    bankroll = db.get_bankroll()
    print(f"    Current balance: ${bankroll['current_balance']:.2f}")
    print(f"    Total deposited: ${bankroll['total_deposited']:.2f}")
    print(f"    In play: ${bankroll['in_play']:.2f}")
    print(f"    Record: {bankroll['wins']}-{bankroll['losses']}")
    print(f"    Net profit: ${bankroll['net_profit']:.2f}")

    conn = db._get_conn()
    for table in ["bets", "parlays", "bankroll_ledger"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"    {table}: {count} rows")

    print(f"\n  Migration complete.")
    print(f"  Database: {db.DB_PATH}")
    print(f"\n  IMPORTANT: Review the data above for accuracy.")
    print(f"  Markdown parsing can be fragile -- spot-check bet history counts")
    print(f"  and bankroll balance against the strategy document.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate betting data to SQLite")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview migration without writing to DB")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
