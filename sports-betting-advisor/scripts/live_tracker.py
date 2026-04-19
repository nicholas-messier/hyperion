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
import sys
import time
from datetime import datetime

import requests

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
    """Return default bets from the current Celtics postseason strategy."""
    return [
        {"player": "Jayson Tatum", "stat": "REB", "target": 10, "wager": 3.00, "parlay_group": "A", "parlay_wager": 2.00},
        {"player": "Jaylen Brown", "stat": "PTS", "target": 25, "wager": 5.00, "parlay_group": "A", "parlay_wager": 2.00},
    ]


def main():
    parser = argparse.ArgumentParser(description="Live bet tracker for Celtics games")
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
    args = parser.parse_args()

    # Parse bets
    if args.bet:
        bets = [parse_bet_string(b) for b in args.bet]
        # No parlay info from CLI by default
        for b in bets:
            b["parlay_group"] = None
            b["parlay_wager"] = 0
    else:
        bets = default_bets()

    # Find the Celtics game
    game_info = find_celtics_game()
    if not game_info:
        print("\n  No Celtics game found on today's scoreboard.")
        print("  Check back on game day.\n")
        sys.exit(0)

    if game_info["status"] == "STATUS_SCHEDULED":
        print(f"\n  Celtics game found but hasn't started yet:")
        print(f"  {game_info['name']}")
        print(f"  Status: {game_info['detail']}")
        print(f"\n  Run this again once the game tips off.\n")
        sys.exit(0)

    event_id = game_info["event_id"]

    while True:
        try:
            summary = get_box_score(event_id)
            status_detail, teams = get_game_score(summary)
            player_stats = get_player_stats(summary, TEAM_ABBR)
            opp_abbr, opp_stats = get_opponent_stats(summary, TEAM_ABBR)

            display_tracker(game_info, status_detail, teams, player_stats, bets, opp_abbr, opp_stats)

            # If game is final, show one last update and exit
            if game_info["status"] == "STATUS_FINAL":
                print("\n  Game is FINAL. Final results above.\n")
                break

            # Re-check game status
            game_info_fresh = find_celtics_game()
            if game_info_fresh:
                game_info["status"] = game_info_fresh["status"]
                game_info["detail"] = game_info_fresh["detail"]

            if args.once:
                break

            time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n\n  Tracker stopped. Go Celtics.\n")
            break
        except requests.RequestException as e:
            print(f"\n  Network error: {e}")
            print(f"  Retrying in {args.interval} seconds...\n")
            if args.once:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
