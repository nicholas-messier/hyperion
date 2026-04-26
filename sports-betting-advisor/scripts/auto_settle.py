#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Auto-Settle — Automatically settle active bets when games go final.

Checks ESPN box scores for final game stats, compares against active bets
in the SQLite database, and settles them (W/L) with proper payout calculation
from stored odds.

Usage:
    # One-shot: settle any bets whose games are final, then exit
    python3 scripts/auto_settle.py

    # Watch mode: keep checking every N seconds until all bets are settled
    python3 scripts/auto_settle.py --watch --interval 60

    # Dry run: show what would be settled without making changes
    python3 scripts/auto_settle.py --dry-run

    # Cron-friendly (no output unless something was settled)
    python3 scripts/auto_settle.py --quiet
"""

import argparse
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Add scripts dir to path so we can import db
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import (
    init_db,
    get_active_bets,
    settle_bet,
    settle_parlay,
    sync_json,
)

# ── ESPN API ─────────────────────────────────────────────────

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# Common abbreviation aliases (DraftKings/standard -> ESPN)
TEAM_ALIASES = {
    "NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO", "UTA": "UTAH",
}
# Reverse map for display
TEAM_ALIASES_REV = {v: k for k, v in TEAM_ALIASES.items()}


def espn_abbr(team: str) -> str:
    """Normalize team abbreviation to ESPN format."""
    return TEAM_ALIASES.get(team, team)


def dk_abbr(team: str) -> str:
    """Convert ESPN abbreviation back to standard/DK format."""
    return TEAM_ALIASES_REV.get(team, team)


# ── Payout math ──────────────────────────────────────────────

def calc_payout(wager: float, odds: int) -> float:
    """Calculate total payout (wager + profit) from American odds.

    DraftKings floors profit to 2 decimal places rather than rounding,
    so we use math.floor to match their payouts exactly.

    Returns 0 if odds are missing/zero (can't calculate).
    """
    if not odds:
        return 0.0
    if odds < 0:
        # e.g., -151 -> profit = wager * (100 / 151)
        profit = wager * (100 / abs(odds))
    else:
        # e.g., +228 -> profit = wager * (228 / 100)
        profit = wager * (odds / 100)
    # DK floors profit to the cent
    profit = math.floor(profit * 100) / 100
    return round(wager + profit, 2)


# ── ESPN data fetching ───────────────────────────────────────

def fetch_scoreboard() -> dict:
    """Fetch today's NBA scoreboard from ESPN."""
    resp = requests.get(SCOREBOARD_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_box_score(event_id: str) -> dict:
    """Fetch full game summary/box score from ESPN."""
    resp = requests.get(SUMMARY_URL, params={"event": event_id}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_final_games(scoreboard: dict) -> dict:
    """Extract final games from scoreboard.

    Returns {team_abbr: event_info} mapping every team in a final game
    to the game's event data.
    """
    finals = {}
    for event in scoreboard.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            continue
        competitors = comp.get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        info = {
            "event_id": event["id"],
            "name": event.get("name", ""),
            "teams": teams,
            "status": status,
        }
        for t in teams:
            finals[t] = info
    return finals


def get_in_progress_games(scoreboard: dict) -> dict:
    """Extract in-progress games from scoreboard.

    Returns {team_abbr: event_info} for games currently being played.
    """
    in_progress = {}
    for event in scoreboard.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_IN_PROGRESS":
            continue
        competitors = comp.get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        detail = comp.get("status", {}).get("type", {}).get("shortDetail", "")
        info = {
            "event_id": event["id"],
            "name": event.get("name", ""),
            "teams": teams,
            "status": status,
            "detail": detail,
        }
        for t in teams:
            in_progress[t] = info
    return in_progress


def extract_player_stats(summary: dict) -> dict:
    """Extract all player stats from a game summary.

    Returns {player_name: {stat: value, ...}}.
    """
    all_stats = {}
    for team_block in summary.get("boxscore", {}).get("players", []):
        stats_block = team_block.get("statistics", [{}])[0]
        labels = stats_block.get("labels", [])
        for athlete in stats_block.get("athletes", []):
            name = athlete.get("athlete", {}).get("displayName", "Unknown")
            raw = athlete.get("stats", [])
            if not raw:
                continue
            parsed = {}
            for i, label in enumerate(labels):
                if i < len(raw):
                    val = raw[i]
                    if "-" in val and label in ("FG", "3PT", "FT"):
                        parts = val.split("-")
                        parsed[label] = int(parts[0])
                        parsed[f"{label}A"] = int(parts[1])
                    elif label == "+/-":
                        parsed[label] = int(val.replace("+", "")) if val else 0
                    else:
                        try:
                            parsed[label] = int(val)
                        except ValueError:
                            parsed[label] = val
            all_stats[name] = parsed
    return all_stats


def get_stat_value(stats: dict, stat_key: str) -> int | None:
    """Get a player's stat value, handling composite stats like PRA."""
    if not stats:
        return None
    if stat_key == "PRA":
        return stats.get("PTS", 0) + stats.get("REB", 0) + stats.get("AST", 0)
    elif stat_key == "3PT":
        return stats.get("3PT", 0)
    else:
        return stats.get(stat_key)


# ── Settlement logic ─────────────────────────────────────────

def settle_active_bets(dry_run: bool = False, quiet: bool = False) -> dict:
    """Check all active bets against final game stats and settle them.

    Returns a summary dict: {settled: int, wins: int, losses: int,
                             pending: int, errors: list}.
    """
    init_db()
    bets, parlays = get_active_bets()

    if not bets:
        if not quiet:
            print("No active bets to settle.")
        return {"settled": 0, "wins": 0, "losses": 0, "pending": 0, "errors": []}

    # Fetch scoreboard
    try:
        scoreboard = fetch_scoreboard()
    except requests.RequestException as e:
        msg = f"Failed to fetch scoreboard: {e}"
        if not quiet:
            print(f"ERROR: {msg}")
        return {"settled": 0, "wins": 0, "losses": 0,
                "pending": len(bets), "errors": [msg]}

    final_games = get_final_games(scoreboard)
    in_progress = get_in_progress_games(scoreboard)

    # Group bets by team to minimize API calls
    team_bets = {}       # espn_team -> [bet, ...]
    parlay_map = {}      # parlay_id -> parlay info
    bet_parlay_legs = {} # parlay_id -> [bet, ...]

    for p in parlays:
        parlay_map[p["id"]] = p

    for bet in bets:
        team = espn_abbr(bet.get("team", ""))
        if team:
            team_bets.setdefault(team, []).append(bet)
        if bet.get("parlay_id"):
            bet_parlay_legs.setdefault(bet["parlay_id"], []).append(bet)

    # Fetch box scores for final games that have active bets
    game_stats = {}  # event_id -> player_stats
    teams_to_fetch = set(team_bets.keys()) & set(final_games.keys())

    for team in teams_to_fetch:
        event_id = final_games[team]["event_id"]
        if event_id in game_stats:
            continue
        try:
            summary = fetch_box_score(event_id)
            game_stats[event_id] = extract_player_stats(summary)
        except requests.RequestException as e:
            if not quiet:
                print(f"  Warning: Could not fetch box score for {final_games[team]['name']}: {e}")

    # Merge all player stats into one dict (players are unique across games)
    all_player_stats = {}
    for stats in game_stats.values():
        all_player_stats.update(stats)

    # Settle individual bets
    results = {"settled": 0, "wins": 0, "losses": 0, "pending": 0, "errors": []}
    settled_bet_ids = set()

    for bet in bets:
        team = espn_abbr(bet.get("team", ""))
        bet_id = bet["id"]

        # Check if this bet's game is final
        if team not in final_games:
            if team in in_progress:
                detail = in_progress[team].get("detail", "in progress")
                if not quiet:
                    print(f"  PENDING: {bet['player']} {bet['target']}+ {bet['stat']}"
                          f" — game still {detail}")
            else:
                if not quiet:
                    print(f"  PENDING: {bet['player']} {bet['target']}+ {bet['stat']}"
                          f" — no game found on today's scoreboard")
            results["pending"] += 1
            continue

        # Look up player stats
        player_stats = all_player_stats.get(bet["player"])
        if player_stats is None:
            if not quiet:
                print(f"  WARNING: {bet['player']} not found in box score"
                      f" for {final_games[team]['name']}")
            results["errors"].append(f"Player not found: {bet['player']}")
            results["pending"] += 1
            continue

        stat_val = get_stat_value(player_stats, bet["stat"])
        if stat_val is None:
            results["errors"].append(
                f"Stat {bet['stat']} not found for {bet['player']}")
            results["pending"] += 1
            continue

        # Determine W/L
        hit = stat_val >= bet["target"]

        # Only settle straight bets (wager > 0 and no parlay_id) directly.
        # Parlay legs (wager = 0, parlay_id set) get settled with their parlay.
        is_straight = bet.get("wager", 0) > 0 and not bet.get("parlay_id")
        is_parlay_leg = bet.get("parlay_id") is not None

        if is_straight:
            if hit:
                payout = calc_payout(bet["wager"], bet.get("odds", 0))
                # Fallback if no odds stored
                if payout == 0:
                    payout = bet["wager"]  # At minimum return the wager
                    if not quiet:
                        print(f"  WARNING: No odds for bet {bet_id}, payout set to wager amount")
                result_str = "W"
                results["wins"] += 1
            else:
                payout = 0
                result_str = "L"
                results["losses"] += 1

            stat_label = "PRA" if bet["stat"] == "PRA" else bet["stat"]
            icon = "W" if hit else "L"
            if not quiet:
                print(f"  {icon}: {bet['player']} {stat_val}/{bet['target']} {stat_label}"
                      f" — ${bet['wager']:.2f} bet"
                      f" -> ${payout:.2f} payout" if hit else
                      f"  {icon}: {bet['player']} {stat_val}/{bet['target']} {stat_label}"
                      f" — ${bet['wager']:.2f} lost")

            if not dry_run:
                settle_bet(bet_id, result_str, payout=payout)
            settled_bet_ids.add(bet_id)
            results["settled"] += 1

        elif is_parlay_leg:
            # Track leg results; parlay settled below
            settled_bet_ids.add(bet_id)

    # Settle parlays
    for parlay_id, legs in bet_parlay_legs.items():
        if parlay_id not in parlay_map:
            continue

        parlay = parlay_map[parlay_id]

        # Check if all legs' games are final
        all_final = True
        for leg in legs:
            team = espn_abbr(leg.get("team", ""))
            if team not in final_games:
                all_final = False
                break

        if not all_final:
            if not quiet:
                leg_names = ", ".join(f"{l['player']} {l['stat']}" for l in legs)
                print(f"  PENDING PARLAY: {leg_names} — not all games final")
            results["pending"] += 1
            continue

        # Evaluate each leg
        leg_results = []
        for leg in legs:
            player_stats = all_player_stats.get(leg["player"])
            if player_stats is None:
                leg_results.append(False)
                continue
            stat_val = get_stat_value(player_stats, leg["stat"])
            if stat_val is None:
                leg_results.append(False)
                continue
            leg_results.append(stat_val >= leg["target"])

        all_hit = all(leg_results)

        if all_hit:
            payout = calc_payout(parlay["wager"], parlay.get("odds", 0))
            if payout == 0:
                payout = parlay["wager"]
                if not quiet:
                    print(f"  WARNING: No odds for parlay {parlay_id},"
                          f" payout set to wager amount")
            result_str = "W"
            results["wins"] += 1
        else:
            payout = 0
            result_str = "L"
            results["losses"] += 1

        leg_summary = " + ".join(
            f"{l['player']} {l['stat']}" for l in legs
        )
        icon = "W" if all_hit else "L"
        if not quiet:
            if all_hit:
                print(f"  {icon}: Parlay ({leg_summary})"
                      f" — ${parlay['wager']:.2f} bet -> ${payout:.2f} payout")
            else:
                # Show which legs missed
                details = []
                for leg, hit in zip(legs, leg_results):
                    ps = all_player_stats.get(leg["player"], {})
                    sv = get_stat_value(ps, leg["stat"])
                    mark = "HIT" if hit else "MISS"
                    details.append(f"{leg['player']} {sv}/{leg['target']} {leg['stat']} ({mark})")
                print(f"  {icon}: Parlay — ${parlay['wager']:.2f} lost")
                for d in details:
                    print(f"       {d}")

        if not dry_run:
            settle_parlay(parlay_id, result_str, payout=payout)
        results["settled"] += 1

    return results


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Auto-settle active bets using ESPN final box scores",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Keep checking until all active bets are settled",
    )
    parser.add_argument(
        "--interval", type=int, default=120,
        help="Seconds between checks in watch mode (default: 120)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be settled without making changes",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print output when bets are actually settled",
    )
    args = parser.parse_args()

    if args.dry_run and not args.quiet:
        print("=== DRY RUN — no changes will be made ===\n")

    while True:
        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        if not args.quiet:
            print(f"[{now}] Checking active bets...")

        try:
            results = settle_active_bets(
                dry_run=args.dry_run, quiet=args.quiet
            )
        except Exception as e:
            if not args.quiet:
                print(f"  Error: {e}")
            if not args.watch:
                sys.exit(1)
            time.sleep(args.interval)
            continue

        if not args.quiet:
            if results["settled"] > 0:
                print(f"\n  Settled: {results['settled']}"
                      f" ({results['wins']}W-{results['losses']}L)")
            if results["pending"] > 0:
                print(f"  Still pending: {results['pending']}")
            if results["errors"]:
                print(f"  Errors: {', '.join(results['errors'])}")
            print()

        # In quiet mode, only print a summary line when something was settled
        if args.quiet and results["settled"] > 0:
            print(f"[{now}] Settled {results['settled']} bets"
                  f" ({results['wins']}W-{results['losses']}L)")

        if not args.watch:
            break

        if results["pending"] == 0:
            if not args.quiet:
                print("All bets settled. Exiting watch mode.")
            break

        if not args.quiet:
            print(f"Waiting {args.interval}s before next check...\n")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
