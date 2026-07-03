#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
update_sports.py — Smart sports display for conky

Shows NBA Playoffs overview with series standings and upcoming games.
When active bets are in progress, shows live bet tracking overlay.

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
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    # requests not installed — always fall back to minimal display
    requests = None

# ESPN API endpoints
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# Config paths
BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
CACHE_DIR = Path.home() / ".cache"
PLAYOFF_CACHE = CACHE_DIR / "nba_playoffs.json"

# Cache TTL for playoff series data (5 minutes)
PLAYOFF_CACHE_TTL = 300

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

LOCAL_TZ = ZoneInfo("America/New_York")

# Common abbreviation aliases (DraftKings/standard -> ESPN)
TEAM_ALIASES = {
    "NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO", "UTA": "UTAH",
}


def espn_abbr(team):
    """Normalize team abbreviation to ESPN format."""
    return TEAM_ALIASES.get(team, team)


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


def format_game_time(date_str):
    """Format a UTC ISO date to compact local time string."""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    local_dt = dt.astimezone(LOCAL_TZ)
    now = datetime.now(LOCAL_TZ)

    t = local_dt.strftime("%-I:%M%p").lower()
    # Clean up :00 for even hours (7:00pm -> 7pm)
    if t.endswith(":00am") or t.endswith(":00pm"):
        t = t.replace(":00", "")

    if local_dt.date() == now.date():
        return f"Today {t}"

    day_diff = (local_dt.date() - now.date()).days
    if 0 < day_diff <= 6:
        return f"{local_dt.strftime('%a')} {t}"

    return f"{local_dt.strftime('%-m/%-d')} {t}"


# ── Playoff data ─────────────────────────────────────────────

def fetch_playoff_series():
    """Fetch all NBA playoff series data from ESPN, with caching."""
    if PLAYOFF_CACHE.exists():
        try:
            cache = json.loads(PLAYOFF_CACHE.read_text())
            if time.time() - cache.get("timestamp", 0) < PLAYOFF_CACHE_TTL:
                return cache["series"]
        except (json.JSONDecodeError, KeyError):
            pass

    # Rolling window: 14 days back, 30 days forward
    now = datetime.now(LOCAL_TZ)
    start = (now - timedelta(days=14)).strftime("%Y%m%d")
    end = (now + timedelta(days=30)).strftime("%Y%m%d")

    resp = requests.get(SCOREBOARD_URL, params={
        "seasontype": "3",
        "dates": f"{start}-{end}",
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    all_events = data.get("events", [])

    # Determine current round from events with active/scheduled games
    round_names = ["1st Round", "2nd Round", "Conf. Finals", "Finals"]
    active_rounds = set()
    for event in all_events:
        comp = event["competitions"][0]
        status = comp["status"]["type"]["name"]
        notes = comp.get("notes", [])
        headline = notes[0].get("headline", "") if notes else ""
        if status in {"STATUS_IN_PROGRESS", "STATUS_SCHEDULED"}:
            for rn in round_names:
                if rn in headline:
                    active_rounds.add(rn)
                    break

    # Pick the earliest active round
    current_round = None
    for rn in round_names:
        if rn in active_rounds:
            current_round = rn
            break

    # Filter events to current round only
    events = []
    for event in all_events:
        notes = event["competitions"][0].get("notes", [])
        headline = notes[0].get("headline", "") if notes else ""
        if current_round and current_round in headline:
            events.append(event)

    if not events:
        events = all_events

    # Group events by series (unique pair of teams)
    series_map = {}
    for event in events:
        comp = event["competitions"][0]
        competitors = comp.get("competitors", [])
        if len(competitors) != 2:
            continue

        abbrs = [c["team"]["abbreviation"] for c in competitors]
        key = tuple(sorted(abbrs))

        if key not in series_map:
            # Higher seed = home team in Game 1 (first event we see)
            notes = comp.get("notes", [])
            headline = notes[0].get("headline", "") if notes else ""
            home = next((c["team"]["abbreviation"] for c in competitors
                         if c.get("homeAway") == "home"), abbrs[0])
            away = next((c["team"]["abbreviation"] for c in competitors
                         if c.get("homeAway") == "away"), abbrs[1])
            series_map[key] = {
                "higher_seed": home,
                "lower_seed": away,
                "headline": headline,
                "games": [],
            }

        status = comp["status"]["type"]["name"]
        detail = comp.get("status", {}).get("type", {}).get("shortDetail", "")
        scores = {c["team"]["abbreviation"]: c.get("score", "0")
                  for c in competitors}

        series_map[key]["games"].append({
            "date": event["date"],
            "status": status,
            "detail": detail,
            "scores": scores,
        })

    # Process into series list with records and next games
    result = []
    for key, info in series_map.items():
        hs, ls = info["higher_seed"], info["lower_seed"]
        hs_wins = ls_wins = 0
        next_game = live_game = None

        for g in sorted(info["games"], key=lambda x: x["date"]):
            if g["status"] == "STATUS_FINAL":
                try:
                    s_hs = int(g["scores"].get(hs, 0))
                    s_ls = int(g["scores"].get(ls, 0))
                except (ValueError, TypeError):
                    continue
                if s_hs > s_ls:
                    hs_wins += 1
                else:
                    ls_wins += 1
            elif g["status"] == "STATUS_IN_PROGRESS" and live_game is None:
                live_game = g
            elif g["status"] == "STATUS_SCHEDULED" and next_game is None:
                next_game = g

        result.append({
            "higher_seed": hs, "lower_seed": ls,
            "hs_wins": hs_wins, "ls_wins": ls_wins,
            "next_game": next_game, "live_game": live_game,
            "headline": info["headline"],
        })

    # Sort by next event date: live games first, then soonest upcoming
    def sort_key(s):
        # Live games sort earliest (prefix "0")
        if s["live_game"]:
            return "0" + s["live_game"]["date"]
        # Then scheduled games by date
        if s["next_game"]:
            return "1" + s["next_game"]["date"]
        # Series with no upcoming game sort last
        return "2"

    result.sort(key=sort_key)

    PLAYOFF_CACHE.write_text(json.dumps({"timestamp": time.time(), "series": result}))
    return result


def get_playoff_record(series_list, team_abbr):
    """Get a team's playoff win-loss from the series data."""
    for s in series_list:
        if team_abbr == s["higher_seed"]:
            return f"{s['hs_wins']}-{s['ls_wins']}"
        if team_abbr == s["lower_seed"]:
            return f"{s['ls_wins']}-{s['hs_wins']}"
    return "?"


# ── Conky output: playoff schedule ───────────────────────────

def print_playoff_header(series_list):
    """Print the NBA Playoffs header with team record."""
    config = read_config()
    team_abbr = config.get("SPORTS_TEAM", "BOS")
    team_name = config.get("SPORTS_TEAM_NAME", "Celtics")
    record = get_playoff_record(series_list, team_abbr) if series_list else "?"

    print(f"${{color #00ff00}}NBA Playoffs${{color}}")
    print(f"${{color #00ff00}}{team_name}: ({record})${{color}}")


def playoff_output(series_list=None):
    """Print NBA Playoffs schedule for conky."""
    config = read_config()
    team_abbr = config.get("SPORTS_TEAM", "BOS")

    # Load active bet teams for highlighting
    bet_teams = set()
    try:
        bets, _ = load_bets()
        bet_teams = {espn_abbr(b["team"]) for b in bets if "team" in b}
    except Exception:
        pass

    if series_list is None:
        try:
            series_list = fetch_playoff_series()
        except Exception:
            series_list = None

    if not series_list:
        print(f"${{color #00ff00}}NBA Playoffs${{color}}")
        print("Schedule unavailable")
        return

    print_playoff_header(series_list)

    for s in series_list:
        hs, ls = s["higher_seed"], s["lower_seed"]
        rec = f"{s['hs_wins']}-{s['ls_wins']}"
        matchup = f"{hs:<3} {rec} {ls:<3}"

        if s["live_game"]:
            detail = s["live_game"]["detail"]
            sc = s["live_game"]["scores"]
            s_hs, s_ls = sc.get(hs, "?"), sc.get(ls, "?")
            print(f"${{color #ff6600}}{matchup}"
                  f"  {s_hs}-{s_ls} {detail}${{color}}")
        elif s["next_game"]:
            when = format_game_time(s["next_game"]["date"])
            if team_abbr in (hs, ls):
                print(f"${{color #add8e6}}{matchup}"
                      f"  {when}${{color}}")
            elif hs in bet_teams or ls in bet_teams:
                print(f"${{color #ffff00}}{matchup}"
                      f"  {when}${{color}}")
            else:
                print(f"{matchup}  {when}")
        else:
            print(f"${{color #888888}}{matchup}  TBD${{color}}")


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


# ── Conky output: live bet tracking ─────────────────────────

def conky_live(games, game_stats, bets, parlays, series_list=None):
    """Print conky-formatted live bet tracking output."""
    print_playoff_header(series_list)

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
            if espn_abbr(bet.get("team", "")) not in game["teams"]:
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
                # Spread / run-line / puck-line targets are floats
                # ('-12.5'); player props are ints. Try int first.
                try:
                    target = int(parts[2])
                except ValueError:
                    try:
                        target = float(parts[2])
                    except ValueError:
                        continue
                for stats in game_stats.values():
                    _, s = eval_bet(stats, parts[0], parts[1], target)
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
    # If requests isn't available, show what we can
    if requests is None:
        playoff_output()
        return

    # Fetch playoff series data (cached, used by both display modes)
    try:
        series_list = fetch_playoff_series()
    except Exception:
        series_list = None

    # Load bets — if none, show playoff schedule
    try:
        bets, parlays = load_bets()
    except Exception:
        playoff_output(series_list)
        return

    if not bets:
        playoff_output(series_list)
        return

    # Check scoreboard for live games with our bet teams
    try:
        scoreboard = get_scoreboard()
    except Exception:
        playoff_output(series_list)
        return

    bet_teams = {espn_abbr(b["team"]) for b in bets if "team" in b}
    games = find_bet_games(scoreboard, bet_teams)

    if not games:
        playoff_output(series_list)
        return

    # Fetch box scores for each matching game
    game_stats = {}
    for game in games:
        try:
            game_stats[game["event_id"]] = get_player_stats(game["event_id"])
        except Exception:
            pass

    conky_live(games, game_stats, bets, parlays, series_list)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort — never show an error in conky
        playoff_output()
