#!/usr/bin/env python3
"""
db.py -- SQLite database module for sports betting advisor.

Single source of truth for bet tracking, bankroll management, and player stats
caching. Stores everything in ~/.config/sports-bets/sports_bets.db.

Usage:
    # As a library
    from db import init_db, record_bet, get_bankroll, settle_bet

    # Verify installation (creates tables, prints schema)
    python3 scripts/db.py
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────

DB_DIR = Path.home() / ".config" / "sports-bets"
DB_PATH = DB_DIR / "sports_bets.db"
BANKROLL_JSON = DB_DIR / "bankroll.json"
ACTIVE_BETS_JSON = DB_DIR / "active_bets.json"

# ── Connection management ────────────────────────────────────

_conn = None


def _get_conn() -> sqlite3.Connection:
    """Get or create a module-level database connection."""
    global _conn
    if _conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), timeout=10)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def close():
    """Close the database connection."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


# ── Schema / init ────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist. Enable WAL mode."""
    conn = _get_conn()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            placed_at   TEXT    NOT NULL,
            player      TEXT    NOT NULL,
            team        TEXT    NOT NULL DEFAULT '',
            sport       TEXT    NOT NULL DEFAULT 'nba',
            stat        TEXT    NOT NULL,
            target      REAL    NOT NULL,
            odds        INTEGER NOT NULL DEFAULT 0,
            wager       REAL    NOT NULL DEFAULT 0,
            confidence  TEXT    NOT NULL DEFAULT '',
            result      TEXT,
            payout      REAL    NOT NULL DEFAULT 0,
            settled_at  TEXT,
            parlay_id   INTEGER REFERENCES parlays(id),
            notes       TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS parlays (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            placed_at   TEXT    NOT NULL,
            odds        INTEGER NOT NULL DEFAULT 0,
            wager       REAL    NOT NULL DEFAULT 0,
            result      TEXT,
            payout      REAL    NOT NULL DEFAULT 0,
            settled_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS bankroll_ledger (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT    NOT NULL,
            action       TEXT    NOT NULL,
            amount       REAL    NOT NULL,
            balance      REAL    NOT NULL,
            reference_id INTEGER,
            notes        TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS player_stats_cache (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name    TEXT    NOT NULL,
            sport          TEXT    NOT NULL DEFAULT 'nba',
            season         TEXT    NOT NULL,
            fetched_at     TEXT    NOT NULL,
            game_log_json  TEXT    NOT NULL DEFAULT '[]',
            averages_json  TEXT    NOT NULL DEFAULT '{}',
            games_played   INTEGER NOT NULL DEFAULT 0
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_player_season
            ON player_stats_cache(player_name, sport, season);
    """)
    conn.commit()


# ── Bet recording ────────────────────────────────────────────

def record_bet(player, stat, target, wager, team="", sport="nba",
               odds=0, confidence="", parlay_id=None, notes="",
               placed_at=None):
    """Insert a new bet and update the bankroll ledger. Returns the bet id."""
    conn = _get_conn()
    ts = placed_at or datetime.now().isoformat()
    cur = conn.execute(
        """INSERT INTO bets
           (placed_at, player, team, sport, stat, target, odds, wager,
            confidence, parlay_id, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, player, team, sport, stat, target, odds, wager,
         confidence, parlay_id, notes),
    )
    bet_id = cur.lastrowid

    # Record bet placement in bankroll ledger (straight bets only, not parlay legs)
    if wager > 0 and parlay_id is None:
        row = conn.execute(
            "SELECT balance FROM bankroll_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        current = row[0] if row else 0
        new_balance = current - wager
        odds_str = f" ({odds:+d})" if odds else ""
        conn.execute(
            """INSERT INTO bankroll_ledger
               (timestamp, action, amount, balance, reference_id, notes)
               VALUES (?, 'bet_placed', ?, ?, ?, ?)""",
            (ts, -wager, new_balance, bet_id,
             f"{player} {target:.0f}+ {stat}{odds_str} ${wager:.2f}"),
        )

    conn.commit()
    sync_json()
    return bet_id


def record_parlay(legs, wager, odds=0, placed_at=None):
    """Insert a parlay and its legs, and update the bankroll ledger.

    Returns the parlay id.
    legs is a list of dicts with keys: player, stat, target, team, sport,
    odds, confidence, notes.
    """
    conn = _get_conn()
    ts = placed_at or datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO parlays (placed_at, odds, wager) VALUES (?, ?, ?)",
        (ts, odds, wager),
    )
    parlay_id = cur.lastrowid

    for leg in legs:
        conn.execute(
            """INSERT INTO bets
               (placed_at, player, team, sport, stat, target, odds, wager,
                confidence, parlay_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, leg["player"], leg.get("team", ""), leg.get("sport", "nba"),
             leg["stat"], leg["target"], leg.get("odds", 0), 0,
             leg.get("confidence", ""), parlay_id, leg.get("notes", "")),
        )

    # Record parlay placement in bankroll ledger
    if wager > 0:
        row = conn.execute(
            "SELECT balance FROM bankroll_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        current = row[0] if row else 0
        new_balance = current - wager
        leg_summary = " + ".join(
            f"{l['player']} {l['stat']}" for l in legs
        )
        odds_str = f" ({odds:+d})" if odds else ""
        conn.execute(
            """INSERT INTO bankroll_ledger
               (timestamp, action, amount, balance, reference_id, notes)
               VALUES (?, 'bet_placed', ?, ?, ?, ?)""",
            (ts, -wager, new_balance, parlay_id,
             f"Parlay: {leg_summary}{odds_str} ${wager:.2f}"),
        )

    conn.commit()
    sync_json()
    return parlay_id


# ── Bet settlement ───────────────────────────────────────────

def settle_bet(bet_id, result, payout=0):
    """Settle a bet (result='W' or 'L') and update the bankroll ledger."""
    conn = _get_conn()
    ts = datetime.now().isoformat()

    # Get the bet
    row = conn.execute("SELECT * FROM bets WHERE id = ?", (bet_id,)).fetchone()
    if not row:
        return False

    conn.execute(
        "UPDATE bets SET result = ?, payout = ?, settled_at = ? WHERE id = ?",
        (result, payout, ts, bet_id),
    )

    # Bankroll ledger entry
    current_balance = get_bankroll()["current_balance"]
    if result == "W":
        net = payout - row["wager"]
        new_balance = current_balance + payout
        action = "bet_settled"
        notes = f"WIN: {row['player']} {row['stat']} {row['target']}+ (${payout:.2f})"
    else:
        net = 0
        new_balance = current_balance
        action = "bet_settled"
        notes = f"LOSS: {row['player']} {row['stat']} {row['target']}+"

    conn.execute(
        """INSERT INTO bankroll_ledger
           (timestamp, action, amount, balance, reference_id, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts, action, payout, new_balance, bet_id, notes),
    )
    conn.commit()
    sync_json()
    return True


def settle_parlay(parlay_id, result, payout=0):
    """Settle a parlay and all its legs."""
    conn = _get_conn()
    ts = datetime.now().isoformat()

    parlay = conn.execute(
        "SELECT * FROM parlays WHERE id = ?", (parlay_id,)
    ).fetchone()
    if not parlay:
        return False

    conn.execute(
        "UPDATE parlays SET result = ?, payout = ?, settled_at = ? WHERE id = ?",
        (result, payout, ts, parlay_id),
    )

    # Mark all legs
    leg_result = "W" if result == "W" else "L"
    conn.execute(
        "UPDATE bets SET result = ?, settled_at = ? WHERE parlay_id = ?",
        (leg_result, ts, parlay_id),
    )

    # Bankroll ledger
    current_balance = get_bankroll()["current_balance"]
    if result == "W":
        new_balance = current_balance + payout
        notes = f"PARLAY WIN (${payout:.2f})"
    else:
        new_balance = current_balance
        notes = "PARLAY LOSS"

    conn.execute(
        """INSERT INTO bankroll_ledger
           (timestamp, action, amount, balance, reference_id, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts, "bet_settled", payout, new_balance, parlay_id, notes),
    )
    conn.commit()
    sync_json()
    return True


# ── Queries ──────────────────────────────────────────────────

def get_active_bets():
    """Get all unsettled bets (result IS NULL).

    Returns a list of dicts compatible with the active_bets.json format.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM bets WHERE result IS NULL ORDER BY placed_at DESC"
    ).fetchall()

    bets = []
    parlays_map = {}

    for r in rows:
        bet = {
            "id": r["id"],
            "player": r["player"],
            "team": r["team"],
            "stat": r["stat"],
            "target": r["target"],
            "wager": r["wager"],
            "odds": r["odds"],
            "confidence": r["confidence"],
            "sport": r["sport"],
            "parlay_id": r["parlay_id"],
        }
        bets.append(bet)

        if r["parlay_id"] and r["parlay_id"] not in parlays_map:
            p = conn.execute(
                "SELECT * FROM parlays WHERE id = ?", (r["parlay_id"],)
            ).fetchone()
            if p:
                parlays_map[r["parlay_id"]] = {
                    "id": p["id"],
                    "wager": p["wager"],
                    "odds": p["odds"],
                }

    return bets, list(parlays_map.values())


def get_bet_history(sport=None, player=None, limit=50):
    """Get settled bet history with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM bets WHERE result IS NOT NULL"
    params = []

    if sport:
        query += " AND sport = ?"
        params.append(sport)
    if player:
        query += " AND player LIKE ?"
        params.append(f"%{player}%")

    query += " ORDER BY settled_at DESC LIMIT ?"
    params.append(limit)

    return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_bankroll():
    """Calculate current bankroll state from the ledger.

    Returns dict with: current_balance, total_deposited, in_play,
    wins, losses, net_profit, starting_bankroll.
    """
    conn = _get_conn()

    # Sum deposits
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM bankroll_ledger WHERE action = 'deposit'"
    ).fetchone()
    total_deposited = row[0]

    # Sum withdrawals
    row = conn.execute(
        "SELECT COALESCE(SUM(ABS(amount)), 0) FROM bankroll_ledger WHERE action = 'withdrawal'"
    ).fetchone()
    total_withdrawn = row[0]

    # Get latest balance from ledger
    row = conn.execute(
        "SELECT balance FROM bankroll_ledger ORDER BY id DESC LIMIT 1"
    ).fetchone()
    current_balance = row[0] if row else 0

    # In play: sum of wagers on unsettled straight bets + unsettled parlays
    row = conn.execute(
        "SELECT COALESCE(SUM(wager), 0) FROM bets WHERE result IS NULL AND parlay_id IS NULL"
    ).fetchone()
    in_play_straight = row[0]

    row = conn.execute(
        "SELECT COALESCE(SUM(wager), 0) FROM parlays WHERE result IS NULL"
    ).fetchone()
    in_play_parlays = row[0]

    in_play = in_play_straight + in_play_parlays

    # W-L record (count straight bets and parlays separately)
    row = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE result = 'W' AND parlay_id IS NULL"
    ).fetchone()
    straight_wins = row[0]
    row = conn.execute(
        "SELECT COUNT(*) FROM bets WHERE result = 'L' AND parlay_id IS NULL"
    ).fetchone()
    straight_losses = row[0]
    row = conn.execute(
        "SELECT COUNT(*) FROM parlays WHERE result = 'W'"
    ).fetchone()
    parlay_wins = row[0]
    row = conn.execute(
        "SELECT COUNT(*) FROM parlays WHERE result = 'L'"
    ).fetchone()
    parlay_losses = row[0]

    wins = straight_wins + parlay_wins
    losses = straight_losses + parlay_losses

    # Starting bankroll = first deposit
    row = conn.execute(
        "SELECT amount FROM bankroll_ledger WHERE action = 'deposit' ORDER BY id LIMIT 1"
    ).fetchone()
    starting_bankroll = row[0] if row else 0

    return {
        "starting_bankroll": starting_bankroll,
        "total_deposited": total_deposited,
        "current_balance": current_balance,
        "in_play": in_play,
        "wins": wins,
        "losses": losses,
        "net_profit": current_balance + in_play - total_deposited,
    }


def update_bankroll(action, amount, notes="", reference_id=None):
    """Add a bankroll ledger entry (deposit, withdrawal, adjustment).

    Returns the new balance.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT balance FROM bankroll_ledger ORDER BY id DESC LIMIT 1"
    ).fetchone()
    current = row[0] if row else 0

    if action == "withdrawal":
        new_balance = current - abs(amount)
        amount = -abs(amount)
    else:
        new_balance = current + amount

    conn.execute(
        """INSERT INTO bankroll_ledger
           (timestamp, action, amount, balance, reference_id, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), action, amount, new_balance,
         reference_id, notes),
    )
    conn.commit()
    sync_json()
    return new_balance


# ── Stats caching ────────────────────────────────────────────

def cache_player_stats(player_name, sport, season, game_log_json,
                       averages_json, games_played):
    """Cache (upsert) player stats. Refreshes fetched_at timestamp."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO player_stats_cache
           (player_name, sport, season, fetched_at, game_log_json,
            averages_json, games_played)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(player_name, sport, season)
           DO UPDATE SET
               fetched_at     = excluded.fetched_at,
               game_log_json  = excluded.game_log_json,
               averages_json  = excluded.averages_json,
               games_played   = excluded.games_played""",
        (player_name, sport, season, datetime.now().isoformat(),
         json.dumps(game_log_json), json.dumps(averages_json), games_played),
    )
    conn.commit()


def get_cached_stats(player_name, sport, season, ttl_hours=24):
    """Get cached stats if they exist and are fresh (within ttl_hours).

    Returns dict with game_log_json, averages_json, games_played, fetched_at
    or None if stale/missing.
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM player_stats_cache
           WHERE player_name = ? AND sport = ? AND season = ?""",
        (player_name, sport, season),
    ).fetchone()

    if not row:
        return None

    fetched = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched > timedelta(hours=ttl_hours):
        return None

    return {
        "game_log_json": json.loads(row["game_log_json"]),
        "averages_json": json.loads(row["averages_json"]),
        "games_played": row["games_played"],
        "fetched_at": row["fetched_at"],
    }


def get_cache_status(player_name, sport, season):
    """Get cache info for a player (regardless of freshness).

    Returns dict or None.
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT fetched_at, games_played FROM player_stats_cache
           WHERE player_name = ? AND sport = ? AND season = ?""",
        (player_name, sport, season),
    ).fetchone()
    if not row:
        return None
    fetched = datetime.fromisoformat(row["fetched_at"])
    age = datetime.now() - fetched
    return {
        "fetched_at": row["fetched_at"],
        "games_played": row["games_played"],
        "age_hours": round(age.total_seconds() / 3600, 1),
        "is_fresh": age < timedelta(hours=24),
    }


def get_frequent_players(limit=10):
    """Get players ranked by how often they've been bet on."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT player, sport, COUNT(*) as bet_count
           FROM bets GROUP BY player, sport
           ORDER BY bet_count DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── JSON sync (backward compat with conky) ───────────────────

def sync_json():
    """Write current state to bankroll.json and active_bets.json.

    Keeps backward compatibility with the conky dashboard and other scripts
    that read the JSON files directly.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)

    # Bankroll
    br = get_bankroll()
    BANKROLL_JSON.write_text(json.dumps({
        "starting_bankroll": br["starting_bankroll"],
        "total_deposited": br["total_deposited"],
        "current_balance": br["current_balance"],
        "in_play": br["in_play"],
        "wins": br["wins"],
        "losses": br["losses"],
    }, indent=4) + "\n")

    # Active bets
    bets, parlays = get_active_bets()

    # Convert to the JSON format expected by live_tracker / conky
    json_bets = []
    parlay_legs = {}  # parlay_id -> list of leg strings
    for b in bets:
        json_bets.append({
            "player": b["player"],
            "team": b["team"],
            "stat": b["stat"],
            "target": b["target"],
            "wager": b["wager"],
            "sport": b.get("sport", "nba"),
        })
        if b["parlay_id"]:
            parlay_legs.setdefault(b["parlay_id"], []).append(
                f"{b['player']}:{b['stat']}:{int(b['target'])}"
            )

    json_parlays = []
    for p in parlays:
        json_parlays.append({
            "name": str(p["id"]),
            "legs": parlay_legs.get(p["id"], []),
            "wager": p["wager"],
        })

    ACTIVE_BETS_JSON.write_text(json.dumps({
        "bets": json_bets,
        "parlays": json_parlays,
    }, indent=4) + "\n")


# ── CLI verification ─────────────────────────────────────────

if __name__ == "__main__":
    print("Initializing database...")
    init_db()

    conn = _get_conn()
    print(f"\nDatabase: {DB_PATH}")
    print(f"Size: {DB_PATH.stat().st_size:,} bytes")

    print("\nTables:")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for t in tables:
        name = t["name"]
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {count} rows")

        # Show columns
        cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
        for c in cols:
            nullable = "" if c["notnull"] else " (nullable)"
            pk = " PK" if c["pk"] else ""
            print(f"    {c['name']}: {c['type']}{pk}{nullable}")

    print("\nDatabase initialized successfully.")
    close()
