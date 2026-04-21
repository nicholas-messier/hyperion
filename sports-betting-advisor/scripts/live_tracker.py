#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Live Bet Tracker — Celtics Postseason
Tracks active bets against real-time player stats via the ESPN scoreboard API.
Free, no API key required.

Usage:
    # Auto-detect live Celtics game, use bets from config
    python3 scripts/live_tracker.py

    # Custom bets on the command line
    python3 scripts/live_tracker.py --bet "Jayson Tatum:REB:10:3.00" --bet "Jaylen Brown:PTS:25:5.00"

    # One-shot (no refresh loop)
    python3 scripts/live_tracker.py --once

    # Custom refresh interval (seconds)
    python3 scripts/live_tracker.py --interval 45

Bet format: "Player Name:STAT:TARGET:WAGER"
  STAT can be: PTS, REB, AST, STL, BLK, 3PT, PRA (pts+reb+ast)
  TARGET is the over threshold (e.g., 10 means 10+)
  WAGER is the dollar amount
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# SQLite database (optional — falls back to JSON if unavailable)
try:
    from db import init_db as _init_db, get_active_bets as _db_get_active_bets, \
        settle_bet as _db_settle_bet, settle_parlay as _db_settle_parlay, \
        sync_json as _db_sync_json
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
TEAM_ABBR = "BOS"

# ESPN box score stat labels in order
STAT_LABELS = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"]

# Map friendly stat names to indices in the ESPN stats array
STAT_INDEX = {
    "MIN": 0, "PTS": 1, "FG": 2, "3PT": 3, "FT": 4,
    "REB": 5, "AST": 6, "TO": 7, "STL": 8, "BLK": 9,
    "OREB": 10, "DREB": 11, "PF": 12, "+/-": 13,
}

# Config / state file paths
BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
PID_FILE = Path.home() / ".cache" / "sports-bets" / "live_tracker.pid"
LOG_FILE = Path.home() / ".cache" / "sports-bets" / "live_tracker.log"

# Common abbreviation aliases (DraftKings/standard -> ESPN)
TEAM_ALIASES = {
    "NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO", "UTA": "UTAH",
}


def espn_abbr(team):
    """Normalize team abbreviation to ESPN format."""
    return TEAM_ALIASES.get(team, team)


def _load_from_db():
    """Try to load active bets from the SQLite database.

    Returns a list of bet dicts (same format as load_active_bets), or None
    if the DB is unavailable or empty.
    """
    if not _HAS_DB:
        return None
    try:
        _init_db()
        bets, parlays = _db_get_active_bets()
        if not bets:
            return None

        result = []
        parlay_map = {p["id"]: p for p in parlays}

        for b in bets:
            entry = {
                "player": b["player"],
                "stat": b["stat"],
                "target": b["target"],
                "wager": b["wager"],
                "team": espn_abbr(b.get("team", "")),
                "parlay_group": None,
                "parlay_wager": 0,
                "db_id": b["id"],
                "db_parlay_id": b.get("parlay_id"),
            }
            if b.get("parlay_id") and b["parlay_id"] in parlay_map:
                entry["parlay_group"] = str(b["parlay_id"])
                entry["parlay_wager"] = parlay_map[b["parlay_id"]]["wager"]
            result.append(entry)

        return result
    except Exception:
        return None


def load_active_bets():
    """Load bets from DB (preferred) or ~/.config/sports-bets/active_bets.json.

    Returns a list of bet dicts with keys: player, stat, target, wager,
    team, parlay_group, parlay_wager.  Returns None if no bets found.
    """
    # Try DB first
    db_bets = _load_from_db()
    if db_bets:
        return db_bets

    # Fall back to JSON
    if not BETS_FILE.exists():
        return None
    try:
        data = json.loads(BETS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    raw_bets = data.get("bets", [])
    parlays = data.get("parlays", [])
    if not raw_bets:
        return None

    result = []
    for b in raw_bets:
        result.append({
            "player": b["player"],
            "stat": b["stat"],
            "target": b["target"],
            "wager": b.get("wager", 0),
            "team": espn_abbr(b.get("team", "")),
            "parlay_group": None,
            "parlay_wager": 0,
        })

    # Match parlay legs back to individual bets
    for p in parlays:
        for leg in p.get("legs", []):
            parts = leg.split(":")
            if len(parts) != 3:
                continue
            p_name, p_stat, p_target = parts[0], parts[1], int(parts[2])
            for entry in result:
                if (entry["player"] == p_name
                        and entry["stat"] == p_stat
                        and entry["target"] == p_target
                        and entry["parlay_group"] is None):
                    entry["parlay_group"] = p.get("name", "?")
                    entry["parlay_wager"] = p.get("wager", 0)
                    break

    return result


def find_active_games(bet_teams):
    """Find today's games involving any of the given team abbreviations.

    Returns a list of game dicts with: event_id, name, status, detail,
    teams, scores, bet_teams.
    """
    resp = requests.get(SCOREBOARD_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    games = []
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        competitors = comp.get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        matching = bet_teams & set(teams)
        if not matching:
            continue
        scores = {c.get("team", {}).get("abbreviation", "???"): c.get("score", "0")
                  for c in competitors}
        games.append({
            "event_id": event["id"],
            "name": event.get("name", ""),
            "status": status,
            "detail": comp.get("status", {}).get("type", {}).get("shortDetail", status),
            "teams": teams,
            "scores": scores,
            "bet_teams": matching,
        })
    return games


def get_all_stats(summary):
    """Extract player stats for BOTH teams from a game summary."""
    all_stats = {}
    for team_block in summary.get("boxscore", {}).get("players", []):
        stats_block = team_block.get("statistics", [{}])[0]
        labels = stats_block.get("labels", STAT_LABELS)
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


def write_pid():
    """Write current PID to the tracker PID file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def remove_pid():
    """Remove PID file if it belongs to this process."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            if pid == os.getpid():
                PID_FILE.unlink(missing_ok=True)
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)


def find_celtics_game():
    """Find the live or most recent Celtics game from today's scoreboard."""
    resp = requests.get(SCOREBOARD_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    for event in data.get("events", []):
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        if TEAM_ABBR in teams:
            status = event["competitions"][0]["status"]["type"]["name"]
            return {
                "event_id": event["id"],
                "name": event["name"],
                "status": status,
                "detail": event["competitions"][0]["status"]["type"].get("shortDetail", status),
            }
    return None


def get_box_score(event_id):
    """Fetch live box score for a game."""
    resp = requests.get(SUMMARY_URL, params={"event": event_id}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_game_score(summary):
    """Extract team scores and game status."""
    header = summary.get("header", {})
    comps = header.get("competitions", [{}])[0]
    status_detail = comps.get("status", {}).get("type", {}).get("shortDetail", "Unknown")

    teams = {}
    for comp in comps.get("competitors", []):
        abbr = comp.get("team", {}).get("abbreviation", "???")
        score = comp.get("score", "0")
        record = comp.get("record", [{}])[0].get("displayValue", "")
        teams[abbr] = {"score": int(score), "record": record}

    return status_detail, teams


def get_player_stats(summary, team_abbr=TEAM_ABBR):
    """Extract player stats for a team from the box score."""
    players_data = summary.get("boxscore", {}).get("players", [])
    for team_block in players_data:
        if team_block.get("team", {}).get("abbreviation") == team_abbr:
            stats_block = team_block.get("statistics", [{}])[0]
            labels = stats_block.get("labels", STAT_LABELS)
            players = {}
            for athlete in stats_block.get("athletes", []):
                name = athlete.get("athlete", {}).get("displayName", "Unknown")
                raw_stats = athlete.get("stats", [])
                if not raw_stats:
                    continue
                parsed = {}
                for i, label in enumerate(labels):
                    if i < len(raw_stats):
                        val = raw_stats[i]
                        # Handle "made-attempted" format (e.g., "7-11")
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
                players[name] = parsed
            return players
    return {}


def get_opponent_stats(summary, team_abbr=TEAM_ABBR):
    """Extract player stats for the opposing team."""
    players_data = summary.get("boxscore", {}).get("players", [])
    for team_block in players_data:
        if team_block.get("team", {}).get("abbreviation") != team_abbr:
            opp_abbr = team_block.get("team", {}).get("abbreviation", "???")
            stats_block = team_block.get("statistics", [{}])[0]
            labels = stats_block.get("labels", STAT_LABELS)
            players = {}
            for athlete in stats_block.get("athletes", []):
                name = athlete.get("athlete", {}).get("displayName", "Unknown")
                raw_stats = athlete.get("stats", [])
                if not raw_stats:
                    continue
                parsed = {}
                for i, label in enumerate(labels):
                    if i < len(raw_stats):
                        val = raw_stats[i]
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
                players[name] = parsed
            return opp_abbr, players
    return "???", {}


def evaluate_bet(player_stats, player_name, stat_key, target):
    """Check a player's current stat against the bet target."""
    stats = player_stats.get(player_name)
    if not stats:
        return None, None, "PLAYER NOT FOUND"

    if stat_key == "PRA":
        current = stats.get("PTS", 0) + stats.get("REB", 0) + stats.get("AST", 0)
    elif stat_key == "3PT":
        current = stats.get("3PT", 0)
    else:
        current = stats.get(stat_key, 0)

    remaining = target - current
    if current >= target:
        return current, 0, "HIT"
    else:
        return current, remaining, "NEEDS MORE"


def parse_bet_string(bet_str):
    """Parse a bet string like 'Jayson Tatum:REB:10:3.00'."""
    parts = bet_str.split(":")
    if len(parts) != 4:
        print(f"  Invalid bet format: {bet_str}")
        print(f"  Expected: 'Player Name:STAT:TARGET:WAGER'")
        sys.exit(1)
    return {
        "player": parts[0].strip(),
        "stat": parts[1].strip().upper(),
        "target": int(parts[2].strip()),
        "wager": float(parts[3].strip()),
    }


def progress_bar(current, target, width=20):
    """Create a visual progress bar."""
    pct = min(current / target, 1.0) if target > 0 else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {current}/{target}"


def clear_screen():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def display_tracker(game_info, status_detail, teams, player_stats, bets, opp_abbr, opp_stats):
    """Display the live bet tracker dashboard."""
    clear_screen()

    now = datetime.now().strftime("%I:%M:%S %p")

    print("=" * 62)
    print("  CELTICS LIVE BET TRACKER")
    print(f"  Last updated: {now}")
    print("=" * 62)

    # Game score
    print()
    bos_score = teams.get("BOS", {}).get("score", 0)
    opp_team = [t for t in teams if t != "BOS"]
    opp_name = opp_team[0] if opp_team else "OPP"
    opp_score = teams.get(opp_name, {}).get("score", 0)

    print(f"  {game_info['name']}")
    print(f"  {'─' * 50}")
    score_line = f"  BOS {bos_score}  —  {opp_name} {opp_score}"
    print(score_line)
    print(f"  {status_detail}")
    print()

    # Active bets
    print(f"  {'─' * 50}")
    print(f"  ACTIVE BETS")
    print(f"  {'─' * 50}")

    total_wagered = 0
    hits = 0

    for i, bet in enumerate(bets, 1):
        player = bet["player"]
        stat = bet["stat"]
        target = bet["target"]
        wager = bet["wager"]
        total_wagered += wager

        current, remaining, status = evaluate_bet(player_stats, player, stat, target)

        if status == "PLAYER NOT FOUND":
            # Check opponent stats
            current, remaining, status = evaluate_bet(opp_stats, player, stat, target)

        if status == "HIT":
            indicator = "✅"
            hits += 1
        elif status == "PLAYER NOT FOUND":
            indicator = "❓"
        else:
            indicator = "⏳"

        stat_label = "PTS+REB+AST" if stat == "PRA" else stat
        print()
        print(f"  {indicator} Bet {i}: {player} — {target}+ {stat_label} (${wager:.2f})")

        if current is not None:
            bar = progress_bar(current, target)
            print(f"     {bar}")
            if status == "HIT":
                over_by = current - target
                print(f"     CASHED {stat_label}: {current} (over by {over_by})")
            else:
                print(f"     Needs {remaining} more {stat_label}")

            # Show relevant extra context
            stats = player_stats.get(player) or opp_stats.get(player, {})
            if stats:
                mins = stats.get("MIN", "?")
                pts = stats.get("PTS", 0)
                reb = stats.get("REB", 0)
                ast = stats.get("AST", 0)
                print(f"     Full line: {pts} PTS / {reb} REB / {ast} AST in {mins} MIN")
        else:
            print(f"     Player not found in box score")

    # Parlay check
    parlay_bets = [b for b in bets if b.get("parlay_group")]
    parlay_groups = {}
    for b in parlay_bets:
        grp = b["parlay_group"]
        if grp not in parlay_groups:
            parlay_groups[grp] = []
        parlay_groups[grp].append(b)

    if parlay_groups:
        print()
        print(f"  {'─' * 50}")
        print(f"  PARLAY STATUS")
        print(f"  {'─' * 50}")
        for grp, grp_bets in parlay_groups.items():
            legs_hit = 0
            total_legs = len(grp_bets)
            for b in grp_bets:
                all_stats = {**player_stats, **opp_stats}
                _, _, status = evaluate_bet(all_stats, b["player"], b["stat"], b["target"])
                if status == "HIT":
                    legs_hit += 1
            parlay_wager = grp_bets[0].get("parlay_wager", 0)
            if legs_hit == total_legs:
                print(f"  ✅ Parlay ({grp}): ALL {total_legs} LEGS HIT — ${parlay_wager:.2f} CASHED")
            else:
                print(f"  ⏳ Parlay ({grp}): {legs_hit}/{total_legs} legs hit — ${parlay_wager:.2f}")

    # Summary
    print()
    print(f"  {'─' * 50}")
    print(f"  SUMMARY")
    print(f"  {'─' * 50}")
    print(f"  Straight bets: {hits}/{len(bets)} hit")
    print(f"  Total wagered: ${total_wagered:.2f}")
    print()
    print(f"  Press Ctrl+C to stop tracking")
    print("=" * 62)


def default_bets():
    """Return default bets — prefer active_bets.json, fall back to hardcoded."""
    loaded = load_active_bets()
    if loaded:
        return loaded
    return [
        {"player": "Tyrese Maxey", "stat": "PTS", "target": 25, "wager": 4.00,
         "team": espn_abbr("PHI")},
        {"player": "Jayson Tatum", "stat": "REB", "target": 10, "wager": 5.00,
         "team": "BOS"},
        {"player": "Jaylen Brown", "stat": "PTS", "target": 25, "wager": 0,
         "team": "BOS", "parlay_group": "A", "parlay_wager": 5.00},
        {"player": "Victor Wembanyama", "stat": "BLK", "target": 3, "wager": 0,
         "team": espn_abbr("SAS"), "parlay_group": "A", "parlay_wager": 5.00},
    ]


def display_multi_tracker(game_info_map, all_stats, bets):
    """Display multi-game tracker in the terminal."""
    clear_screen()
    now = datetime.now().strftime("%I:%M:%S %p")

    print("=" * 62)
    print("  LIVE BET TRACKER")
    print(f"  Last updated: {now}")
    print("=" * 62)

    # Game scores
    for info in game_info_map.values():
        print()
        teams = info["teams"]
        names = list(teams.keys())
        if len(names) == 2:
            t1, t2 = names
            s1 = teams[t1].get("score", 0)
            s2 = teams[t2].get("score", 0)
            print(f"  {t1} {s1}  \u2014  {t2} {s2}")
        print(f"  {info['detail']}")

    # Bets
    print()
    print(f"  {'\u2500' * 50}")
    print("  ACTIVE BETS")
    print(f"  {'\u2500' * 50}")

    total_wagered = 0
    hits = 0

    # Only show straight bets (wager > 0), not parlay-only legs
    straight_bets = [b for b in bets if b.get("wager", 0) > 0]
    for i, bet in enumerate(straight_bets, 1):
        player = bet["player"]
        stat = bet["stat"]
        target = bet["target"]
        wager = bet.get("wager", 0)
        total_wagered += wager

        current, remaining, status = evaluate_bet(all_stats, player, stat, target)

        if status == "HIT":
            indicator = "\u2705"
            hits += 1
        elif status == "PLAYER NOT FOUND":
            indicator = "\u2753"
        else:
            indicator = "\u23f3"

        stat_label = "PTS+REB+AST" if stat == "PRA" else stat
        print()
        print(f"  {indicator} Bet {i}: {player} \u2014 {target}+ {stat_label} (${wager:.2f})")

        if current is not None:
            bar = progress_bar(current, target)
            print(f"     {bar}")
            if status == "HIT":
                print(f"     CASHED {stat_label}: {current} (over by {current - target})")
            else:
                print(f"     Needs {remaining} more {stat_label}")
            p_stats = all_stats.get(player, {})
            if p_stats:
                mins = p_stats.get("MIN", "?")
                pts = p_stats.get("PTS", 0)
                reb = p_stats.get("REB", 0)
                ast = p_stats.get("AST", 0)
                print(f"     Full line: {pts} PTS / {reb} REB / {ast} AST in {mins} MIN")
        else:
            print("     Player not found in box score")

    # Parlay status
    parlay_groups = {}
    for b in bets:
        grp = b.get("parlay_group")
        if grp:
            parlay_groups.setdefault(grp, []).append(b)

    if parlay_groups:
        print()
        print(f"  {'\u2500' * 50}")
        print("  PARLAY STATUS")
        print(f"  {'\u2500' * 50}")
        for grp, grp_bets in parlay_groups.items():
            legs_hit = sum(
                1 for b in grp_bets
                if evaluate_bet(all_stats, b["player"], b["stat"], b["target"])[2] == "HIT"
            )
            total_legs = len(grp_bets)
            wager = grp_bets[0].get("parlay_wager", 0)
            if legs_hit == total_legs:
                print(f"  \u2705 Parlay ({grp}): ALL {total_legs} LEGS HIT \u2014 ${wager:.2f} CASHED")
            else:
                print(f"  \u23f3 Parlay ({grp}): {legs_hit}/{total_legs} legs hit \u2014 ${wager:.2f}")

    # Summary
    print()
    print(f"  {'\u2500' * 50}")
    parlay_total = sum(w for w in {b.get("parlay_group"): b.get("parlay_wager", 0)
                                    for b in bets if b.get("parlay_group")}.values())
    total_display = total_wagered + parlay_total
    print(f"  Straight bets: {hits}/{len(straight_bets)} hit | Total wagered: ${total_display:.2f}")
    print()
    print("  Press Ctrl+C to stop tracking")
    print("=" * 62)


def write_daemon_output(game_info_map, all_stats, bets):
    """Write tracker state to log file (daemon mode)."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    now = datetime.now().strftime("%I:%M:%S %p")
    lines.append("=== LIVE BET TRACKER (Auto) ===")
    lines.append(f"Updated: {now}")
    lines.append("")

    for info in game_info_map.values():
        teams = info["teams"]
        names = list(teams.keys())
        if len(names) == 2:
            t1, t2 = names
            s1 = teams[t1].get("score", 0)
            s2 = teams[t2].get("score", 0)
            lines.append(f"GAME: {t1} {s1} - {t2} {s2}  ({info['detail']})")

    lines.append("")

    # Only show straight bets (wager > 0), not parlay-only legs
    for i, bet in enumerate(bets, 1):
        if bet.get("wager", 0) <= 0:
            continue
        current, remaining, status = evaluate_bet(
            all_stats, bet["player"], bet["stat"], bet["target"])
        stat_label = "PRA" if bet["stat"] == "PRA" else bet["stat"]
        icon = {
            "HIT": "\u2713",
            "NEEDS MORE": "\u25c6",
            "PLAYER NOT FOUND": "?",
        }.get(status, "?")
        if current is not None:
            lines.append(
                f"  {icon} ${bet['wager']:.0f} {bet['player']} "
                f"{stat_label} {current}/{bet['target']}"
            )
        else:
            lines.append(
                f"  ? ${bet['wager']:.0f} {bet['player']} "
                f"{stat_label} ?/{bet['target']}"
            )

    # Parlay status
    parlay_groups = {}
    for b in bets:
        grp = b.get("parlay_group")
        if grp:
            parlay_groups.setdefault(grp, []).append(b)
    for grp, grp_bets in parlay_groups.items():
        legs_hit = sum(
            1 for b in grp_bets
            if evaluate_bet(all_stats, b["player"], b["stat"], b["target"])[2] == "HIT"
        )
        wager = grp_bets[0].get("parlay_wager", 0)
        lines.append(
            f"  Parlay {grp}: {legs_hit}/{len(grp_bets)} legs (${wager:.0f})"
        )

    LOG_FILE.write_text("\n".join(lines) + "\n")


def _auto_settle_bets(bets, all_stats):
    """Auto-settle bets in the DB when all games are final.

    Only runs if the DB module is available and bets have db_id fields.
    """
    if not _HAS_DB:
        return

    settled = 0
    for bet in bets:
        db_id = bet.get("db_id")
        if not db_id:
            continue

        current, remaining, status = evaluate_bet(all_stats, bet["player"],
                                                   bet["stat"], bet["target"])
        if status == "HIT":
            # Rough payout estimate (we don't have exact odds in all cases)
            _db_settle_bet(db_id, "W", payout=bet.get("wager", 0) * 1.5)
            settled += 1
        elif status == "NEEDS MORE":
            _db_settle_bet(db_id, "L", payout=0)
            settled += 1

    # Settle parlays
    parlay_groups = {}
    for b in bets:
        grp = b.get("parlay_group")
        if grp and b.get("db_parlay_id"):
            parlay_groups.setdefault(b["db_parlay_id"], []).append(b)

    for parlay_id, legs in parlay_groups.items():
        all_hit = all(
            evaluate_bet(all_stats, b["player"], b["stat"], b["target"])[2] == "HIT"
            for b in legs
        )
        if all_hit:
            wager = legs[0].get("parlay_wager", 0)
            _db_settle_parlay(parlay_id, "W", payout=wager * 2.5)
        else:
            _db_settle_parlay(parlay_id, "L", payout=0)
        settled += 1

    if settled:
        try:
            _db_sync_json()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Live bet tracker — tracks active bets against real-time stats",
    )
    parser.add_argument(
        "--bet", "-b", action="append", default=None,
        help="Bet in format 'Player:STAT:TARGET:WAGER' (can specify multiple)",
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=30,
        help="Refresh interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run once and exit (no refresh loop)",
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Background mode: write state to log file, manage PID",
    )
    args = parser.parse_args()

    # ── Daemon housekeeping ──────────────────────────────────
    if args.daemon:
        write_pid()

        def _cleanup(signum, frame):
            remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _cleanup)
        signal.signal(signal.SIGINT, _cleanup)

    def _print(msg):
        """Print only in interactive (non-daemon) mode."""
        if not args.daemon:
            print(msg)

    # ── Load bets ────────────────────────────────────────────
    if args.bet:
        bets = [parse_bet_string(b) for b in args.bet]
        for b in bets:
            b.setdefault("team", "")
            b.setdefault("parlay_group", None)
            b.setdefault("parlay_wager", 0)
    else:
        bets = default_bets()

    if not bets:
        _print("\n  No bets to track.\n")
        if args.daemon:
            remove_pid()
        return

    # ── Discover games ───────────────────────────────────────
    bet_teams = {b["team"] for b in bets if b.get("team")}

    if bet_teams:
        # Multi-team mode: find all games with bet teams
        games = find_active_games(bet_teams)
    else:
        # Legacy single-team mode (no team info in bets)
        game_info = find_celtics_game()
        if game_info:
            games = [{
                "event_id": game_info["event_id"],
                "name": game_info["name"],
                "status": game_info["status"],
                "detail": game_info["detail"],
                "teams": ["BOS"],
                "scores": {},
                "bet_teams": {"BOS"},
            }]
        else:
            games = []

    if not games:
        _print("\n  No games found for tracked teams on today's scoreboard.\n")
        if args.daemon:
            remove_pid()
        return

    # Ensure at least one game is in progress or final
    playable = [g for g in games
                if g["status"] in ("STATUS_IN_PROGRESS", "STATUS_FINAL")]
    if not playable:
        scheduled = [g for g in games if g["status"] == "STATUS_SCHEDULED"]
        if scheduled:
            _print("\n  Games found but not started yet:")
            for g in scheduled:
                _print(f"    {g['name']} \u2014 {g['detail']}")
            _print("\n  Run again once a game tips off.\n")
        if args.daemon:
            remove_pid()
        return

    # ── Main tracking loop ───────────────────────────────────
    while True:
        try:
            # Fetch box scores from every active game
            all_player_stats = {}
            game_info_map = {}

            for game in games:
                if game["status"] not in ("STATUS_IN_PROGRESS", "STATUS_FINAL"):
                    continue
                try:
                    summary = get_box_score(game["event_id"])
                    detail, team_scores = get_game_score(summary)
                    game_info_map[game["event_id"]] = {
                        "name": game["name"],
                        "detail": detail,
                        "teams": team_scores,
                        "status": game["status"],
                    }
                    all_player_stats.update(get_all_stats(summary))
                except Exception:
                    pass

            # Render output
            if args.daemon:
                write_daemon_output(game_info_map, all_player_stats, bets)
            elif bet_teams:
                display_multi_tracker(game_info_map, all_player_stats, bets)
            else:
                # Single-game legacy display (BOS only)
                eid = games[0]["event_id"]
                summary = get_box_score(eid)
                status_detail, teams = get_game_score(summary)
                player_stats = get_player_stats(summary, TEAM_ABBR)
                opp_abbr, opp_stats = get_opponent_stats(summary, TEAM_ABBR)
                display_tracker(games[0], status_detail, teams,
                                player_stats, bets, opp_abbr, opp_stats)

            # All tracked games final? Settle bets and exit.
            active = [g for g in games
                      if g["status"] in ("STATUS_IN_PROGRESS", "STATUS_FINAL")]
            if active and all(g["status"] == "STATUS_FINAL" for g in active):
                _print("\n  All tracked games are FINAL. Results above.\n")
                _auto_settle_bets(bets, all_player_stats)
                break

            # Refresh game statuses
            if bet_teams:
                for rg in find_active_games(bet_teams):
                    for g in games:
                        if g["event_id"] == rg["event_id"]:
                            g["status"] = rg["status"]
                            g["detail"] = rg["detail"]
                            g["scores"] = rg["scores"]
            else:
                fresh = find_celtics_game()
                if fresh:
                    games[0]["status"] = fresh["status"]
                    games[0]["detail"] = fresh["detail"]

            if args.once:
                break

            time.sleep(args.interval)

        except KeyboardInterrupt:
            _print("\n\n  Tracker stopped.\n")
            break
        except requests.RequestException as e:
            _print(f"\n  Network error: {e}")
            _print(f"  Retrying in {args.interval} seconds...\n")
            if args.once:
                break
            time.sleep(args.interval)

    if args.daemon:
        remove_pid()


if __name__ == "__main__":
    main()
