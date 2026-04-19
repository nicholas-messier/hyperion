#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
update_sports.py — Smart sports display for conky

Shows live bet tracking when games with active bets are in progress,
otherwise shows the next Celtics game schedule.

Called from conky's execpi every 60 seconds:
    ${execpi 60 python3 /path/to/update_sports.py}

Active bets are read from ~/.config/sports-bets/active_bets.json

Example active_bets.json:
{
    "bets": [
        {"player": "Jaylen Brown", "team": "BOS", "stat": "PTS", "target": 25, "wager": 5.00},
        {"player": "Jayson Tatum", "team": "BOS", "stat": "REB", "target": 10, "wager": 3.00}
    ],
    "parlays": [
        {"name": "A", "legs": ["Jaylen Brown:PTS:25", "Jayson Tatum:REB:10"], "wager": 2.00}
    ]
}
"""

import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    # requests not installed — always fall back to cached schedule
    requests = None

# ESPN API endpoints
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# Config paths
BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
CACHE_DIR = Path.home() / ".cache"
RECORD_CACHE = CACHE_DIR / "celtics_record.txt"
NEXT_CACHE = CACHE_DIR / "celtics_next.txt"

# Read config.env from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_ENV = SCRIPT_DIR.parent / "config.env"

# Game statuses that trigger bet tracking display
TRACKABLE = {"STATUS_IN_PROGRESS", "STATUS_FINAL"}

# ESPN box score stat labels (default order)
STAT_LABELS = [
    "MIN", "PTS", "FG", "3PT", "FT", "REB", "AST",
    "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-",
]


# ── Helpers ──────────────────────────────────────────────────

def read_config():
    """Read config.env key=value pairs."""
    config = {}
    if CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                config[key.strip()] = val.strip().strip('"')
    return config


def cached_record():
    """Read the cached team record string."""
    try:
        return RECORD_CACHE.read_text().strip()
    except FileNotFoundError:
        return "?"


def schedule_output():
    """Print the cached schedule display (fallback when no live bets)."""
    config = read_config()
    team_name = config.get("SPORTS_TEAM_NAME", "Celtics")
    record = cached_record()

    print(f"${{color #00ff00}}{team_name}: ({record})${{color}}")
    try:
        print(NEXT_CACHE.read_text().strip())
    except FileNotFoundError:
        print("No upcoming games")


# ── Data loading ─────────────────────────────────────────────

def load_bets():
    """Load active bets and parlays from the JSON config file."""
    if not BETS_FILE.exists():
        return [], []
    data = json.loads(BETS_FILE.read_text())
    return data.get("bets", []), data.get("parlays", [])


# ── ESPN API ─────────────────────────────────────────────────

def get_scoreboard():
    """Fetch today's NBA scoreboard."""
    resp = requests.get(SCOREBOARD_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def find_bet_games(scoreboard, bet_teams):
    """Find live or final games that involve teams with active bets."""
    games = []
    for event in scoreboard.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status_name = comp.get("status", {}).get("type", {}).get("name", "")
        if status_name not in TRACKABLE:
            continue

        competitors = comp.get("competitors", [])
        game_teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        if not any(t in bet_teams for t in game_teams):
            continue

        scores = {}
        for c in competitors:
            abbr = c.get("team", {}).get("abbreviation", "???")
            scores[abbr] = c.get("score", "0")

        detail = comp.get("status", {}).get("type", {}).get("shortDetail", "")
        games.append({
            "event_id": event["id"],
            "short_name": event.get("shortName", ""),
            "status": status_name,
            "detail": detail,
            "teams": game_teams,
            "scores": scores,
        })
    return games


def get_player_stats(event_id):
    """Fetch box score and extract all player stats for a game."""
    resp = requests.get(SUMMARY_URL, params={"event": event_id}, timeout=10)
    resp.raise_for_status()
    summary = resp.json()

    stats = {}
    for team_block in summary.get("boxscore", {}).get("players", []):
        labels = team_block.get("statistics", [{}])[0].get("labels", STAT_LABELS)
        for athlete in team_block.get("statistics", [{}])[0].get("athletes", []):
            name = athlete.get("athlete", {}).get("displayName", "Unknown")
            raw = athlete.get("stats", [])
            if not raw:
                continue
            parsed = {}
            for i, label in enumerate(labels):
                if i < len(raw):
                    val = raw[i]
                    if "-" in val and label in ("FG", "3PT", "FT"):
                        parsed[label] = int(val.split("-")[0])
                    elif label == "+/-":
                        parsed[label] = int(val.replace("+", "")) if val else 0
                    else:
                        try:
                            parsed[label] = int(val)
                        except ValueError:
                            parsed[label] = val
            stats[name] = parsed
    return stats


# ── Bet evaluation ───────────────────────────────────────────

def eval_bet(all_stats, player, stat, target):
    """Evaluate a bet against current player stats.

    Returns (current_value, status_string).
    status is "HIT", "LIVE", or "?" if player not found.
    """
    p_stats = all_stats.get(player)
    if not p_stats:
        return None, "?"

    if stat == "PRA":
        cur = p_stats.get("PTS", 0) + p_stats.get("REB", 0) + p_stats.get("AST", 0)
    else:
        cur = p_stats.get(stat, 0)

    return cur, ("HIT" if cur >= target else "LIVE")


# ── Conky output formatting ─────────────────────────────────

def conky_live(games, game_stats, bets, parlays):
    """Print conky-formatted live bet tracking output."""
    config = read_config()
    team_name = config.get("SPORTS_TEAM_NAME", "Celtics")
    record = cached_record()

    # Header — always show the home team name and record
    print(f"${{color #00ff00}}{team_name}: ({record})${{color}}")

    for game in games:
        teams = list(game["scores"].keys())
        s0, s1 = game["scores"][teams[0]], game["scores"][teams[1]]

        if game["status"] == "STATUS_FINAL":
            print(f"${{color #888888}}FINAL${{color}} {teams[0]} {s0}-{teams[1]} {s1}")
        else:
            print(f"${{color #ff6600}}LIVE${{color}}  {teams[0]} {s0}-{teams[1]} {s1} {game['detail']}")

        # Evaluate bets for this game
        stats = game_stats.get(game["event_id"], {})
        for bet in bets:
            if bet.get("team") not in game["teams"]:
                continue

            player = bet["player"]
            stat = bet["stat"]
            target = bet["target"]
            short = player.split()[-1] if " " in player else player
            label = "PRA" if stat == "PRA" else stat

            cur, status = eval_bet(stats, player, stat, target)

            if cur is None:
                print(f"${{color #888888}}  ? {short} {target}+ {label}${{color}}")
            elif status == "HIT":
                print(f"${{color #00ff00}}  \u2713 {short} {label} {cur}/{target}${{color}}")
            else:
                print(f"${{color #ffff00}}  \u25c6 {short} {label} {cur}/{target}${{color}}")

    # Parlay status
    for parlay in parlays:
        legs = parlay.get("legs", [])
        hits = 0
        for leg in legs:
            parts = leg.split(":")
            if len(parts) == 3:
                for stats in game_stats.values():
                    _, s = eval_bet(stats, parts[0], parts[1], int(parts[2]))
                    if s == "HIT":
                        hits += 1
                        break
        name = parlay.get("name", "")
        total = len(legs)
        prefix = f"  Parlay{' ' + name if name else ''}"
        if hits == total and total > 0:
            print(f"${{color #00ff00}}{prefix}: {hits}/{total} HIT${{color}}")
        else:
            print(f"${{color #add8e6}}{prefix}: {hits}/{total} legs${{color}}")


# ── Main ─────────────────────────────────────────────────────

def main():
    # If requests isn't available, always show schedule
    if requests is None:
        schedule_output()
        return

    # Load bets — if none, show schedule
    try:
        bets, parlays = load_bets()
    except Exception:
        schedule_output()
        return

    if not bets:
        schedule_output()
        return

    # Check scoreboard for live games with our bet teams
    try:
        scoreboard = get_scoreboard()
    except Exception:
        schedule_output()
        return

    bet_teams = {b["team"] for b in bets if "team" in b}
    games = find_bet_games(scoreboard, bet_teams)

    if not games:
        schedule_output()
        return

    # Fetch box scores for each matching game
    game_stats = {}
    for game in games:
        try:
            game_stats[game["event_id"]] = get_player_stats(game["event_id"])
        except Exception:
            pass

    conky_live(games, game_stats, bets, parlays)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort — never show an error in conky
        schedule_output()
