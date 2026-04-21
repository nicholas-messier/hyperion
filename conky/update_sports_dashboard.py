#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
update_sports_dashboard.py — Full sports panel for conky

Outputs three sections:
1. NBA Playoffs — series matchups, scores, next games
2. Active Bets — current open bets with live progress
3. Bankroll Status — balance, net P/L, W-L record

Called from conky's execpi every 60 seconds:
    ${execpi 60 python3 /path/to/update_sports_dashboard.py}
"""

import json
import os
import signal as signal_mod
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    requests = None

# ESPN API endpoints
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# Config paths
BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
BANKROLL_FILE = Path.home() / ".config" / "sports-bets" / "bankroll.json"
CACHE_DIR = Path.home() / ".cache"
PLAYOFF_CACHE = CACHE_DIR / "nba_playoffs.json"

# Cache TTL for playoff series data (5 minutes)
PLAYOFF_CACHE_TTL = 300

# Read config.env from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_ENV = SCRIPT_DIR.parent / "config.env"

# Game statuses that trigger bet tracking display
# Include halftime / end-of-period — game is still live, just on a break
TRACKABLE = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_FINAL"}
LIVE_STATUSES = {"STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_END_PERIOD"}

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
        if status in LIVE_STATUSES | {"STATUS_SCHEDULED"}:
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
            elif g["status"] in LIVE_STATUSES and live_game is None:
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
        if s["live_game"]:
            return "0" + s["live_game"]["date"]
        if s["next_game"]:
            return "1" + s["next_game"]["date"]
        return "2"

    result.sort(key=sort_key)

    PLAYOFF_CACHE.write_text(json.dumps({"timestamp": time.time(), "series": result}))
    return result


def patch_series_with_live_data(series_list, scoreboard):
    """Update cached series with fresh live game data from today's scoreboard.

    The playoff cache may be up to 5 minutes stale, so games that just tipped
    off can be missing from live_game.  This patches them in using the always-
    fresh scoreboard response and re-sorts so live games appear first.
    """
    if not series_list or not scoreboard:
        return

    patched = False
    for event in scoreboard.get("events", []):
        comp = event["competitions"][0]
        status_name = comp.get("status", {}).get("type", {}).get("name", "")
        if status_name not in LIVE_STATUSES:
            continue

        competitors = comp.get("competitors", [])
        game_teams = {c["team"]["abbreviation"] for c in competitors}
        scores = {c["team"]["abbreviation"]: c.get("score", "0")
                  for c in competitors}
        detail = comp.get("status", {}).get("type", {}).get("shortDetail", "")

        for s in series_list:
            if s["higher_seed"] in game_teams and s["lower_seed"] in game_teams:
                s["live_game"] = {
                    "date": event["date"],
                    "status": status_name,
                    "detail": detail,
                    "scores": scores,
                }
                patched = True
                break

    if patched:
        def sort_key(s):
            if s["live_game"]:
                return "0" + s["live_game"]["date"]
            if s["next_game"]:
                return "1" + s["next_game"]["date"]
            return "2"
        series_list.sort(key=sort_key)


def get_playoff_record(series_list, team_abbr):
    """Get a team's playoff win-loss from the series data."""
    for s in series_list:
        if team_abbr == s["higher_seed"]:
            return f"{s['hs_wins']}-{s['ls_wins']}"
        if team_abbr == s["lower_seed"]:
            return f"{s['ls_wins']}-{s['hs_wins']}"
    return "?"


# ── Data loading ─────────────────────────────────────────────

def load_bets():
    """Load active bets and parlays from the JSON config file."""
    if not BETS_FILE.exists():
        return [], []
    data = json.loads(BETS_FILE.read_text())
    return data.get("bets", []), data.get("parlays", [])


def load_bankroll():
    """Load bankroll data from the JSON config file."""
    if not BANKROLL_FILE.exists():
        return None
    try:
        return json.loads(BANKROLL_FILE.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


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


# ── Section 1: Playoff output ───────────────────────────────

def print_playoff_section(series_list):
    """Print NBA Playoffs section for conky."""
    config = read_config()
    team_abbr = config.get("SPORTS_TEAM", "BOS")
    team_name = config.get("SPORTS_TEAM_NAME", "Celtics")

    # Load active bet teams for highlighting
    bet_teams = set()
    try:
        bets, _ = load_bets()
        bet_teams = {espn_abbr(b["team"]) for b in bets if "team" in b}
    except Exception:
        pass

    if not series_list:
        print(f"${{color #00ff00}}NBA Playoffs${{color}}")
        print("Schedule unavailable")
        return

    record = get_playoff_record(series_list, team_abbr)
    print(f"${{color #00ff00}}NBA Playoffs${{color}}")
    print(f"${{color #00ff00}}{team_name}: ({record})${{color}}")

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


# ── Section 2: Active bets output ───────────────────────────

def print_bets_section(bets, parlays, game_stats, games):
    """Print Active Bets section for conky."""
    print(f"${{color #888888}}--------------------------------${{color}}")

    if not bets:
        print(f"${{color #888888}}No active bets${{color}}")
        return

    # Calculate total in play
    total_wager = sum(b.get("wager", 0) for b in bets)
    total_wager += sum(p.get("wager", 0) for p in parlays)
    print(f"${{color #add8e6}}Active Bets${{color}}  $${total_wager:.0f} in play")

    # Build a map of which games are live/final for quick lookup
    live_teams = set()
    for g in games:
        if g["status"] in TRACKABLE:
            live_teams.update(g["teams"])

    for bet in bets:
        player = bet["player"]
        stat = bet["stat"]
        target = bet["target"]
        wager = bet.get("wager", 0)
        team = espn_abbr(bet.get("team", ""))
        short = player.split()[-1] if " " in player else player
        label = "PRA" if stat == "PRA" else stat

        # Check if this bet's game is live and we have stats
        if team in live_teams and game_stats:
            # Find stats from the matching game
            cur, status = None, "?"
            for g in games:
                if team in g["teams"] and g["event_id"] in game_stats:
                    cur, status = eval_bet(game_stats[g["event_id"]],
                                           player, stat, target)
                    break

            if cur is None:
                print(f"${{color #888888}}  ? $${wager:.0f} {short} {target}+ {label}${{color}}")
            elif status == "HIT":
                print(f"${{color #00ff00}}  \u2713 $${wager:.0f} {short} {label} {cur}/{target}${{color}}")
            else:
                print(f"${{color #ffff00}}  \u25c6 $${wager:.0f} {short} {label} {cur}/{target}${{color}}")
        else:
            # Static display — no live game
            print(f"  $${wager:.0f} {short} {target}+ {label}")

    # Parlay status
    for parlay in parlays:
        legs = parlay.get("legs", [])
        wager = parlay.get("wager", 0)
        name = parlay.get("name", "")
        hits = 0
        total = len(legs)

        for leg in legs:
            parts = leg.split(":")
            if len(parts) == 3:
                for stats in game_stats.values():
                    _, s = eval_bet(stats, parts[0], parts[1], int(parts[2]))
                    if s == "HIT":
                        hits += 1
                        break

        prefix = f"  $${wager:.0f} Parlay{' ' + name if name else ''}"
        if hits == total and total > 0:
            print(f"${{color #00ff00}}{prefix}: {hits}/{total} HIT${{color}}")
        elif hits > 0:
            print(f"${{color #add8e6}}{prefix}: {hits}/{total} legs${{color}}")
        else:
            print(f"{prefix}: {hits}/{total} legs")


# ── Section 3: Bankroll output ───────────────────────────────

def print_bankroll_section(bankroll):
    """Print Bankroll Status section for conky."""
    print(f"${{color #888888}}--------------------------------${{color}}")

    if bankroll is None:
        print(f"${{color #888888}}Bankroll: N/A${{color}}")
        return

    balance = bankroll.get("current_balance", 0)
    deposited = bankroll.get("total_deposited", 0)
    starting = bankroll.get("starting_bankroll", 0)
    in_play = bankroll.get("in_play", 0)
    wins = bankroll.get("wins", 0)
    losses = bankroll.get("losses", 0)

    net = balance + in_play - deposited

    # Balance color: green if above starting, red if below
    if balance >= starting:
        bal_color = "#00ff00"
    else:
        bal_color = "#ff4444"

    # Net color
    if net >= 0:
        net_str = f"+$${net:.2f}"
        net_color = "#00ff00"
    else:
        net_str = f"-$${abs(net):.2f}"
        net_color = "#ff4444"

    print(f"${{color {bal_color}}}Bankroll: $${balance:.2f}${{color}}")
    print(f"${{color {net_color}}}Net: {net_str}${{color}}  Record: {wins}-{losses}")
    if in_play > 0:
        print(f"In Play: $${in_play:.2f}")


# ── Live tracker process management ──────────────────────────

TRACKER_SCRIPT = SCRIPT_DIR.parent / "sports-betting-advisor" / "scripts" / "live_tracker.py"
TRACKER_PID = Path.home() / ".cache" / "sports-bets" / "live_tracker.pid"


def _tracker_running():
    """Check if the live tracker daemon is alive. Cleans stale PID file."""
    if not TRACKER_PID.exists():
        return False
    try:
        pid = int(TRACKER_PID.read_text().strip())
        os.kill(pid, 0)  # signal 0 = existence check
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        TRACKER_PID.unlink(missing_ok=True)
        return False


def manage_live_tracker(games):
    """Start or stop the live tracker daemon based on game status.

    Called at the end of every dashboard refresh (60 s cycle).
    - If any bet game is IN_PROGRESS and tracker is not running → start it.
    - If no games are IN_PROGRESS and tracker IS running → stop it.
    """
    if not TRACKER_SCRIPT.exists():
        return

    any_live = any(g["status"] in LIVE_STATUSES for g in games)

    if any_live and not _tracker_running():
        TRACKER_PID.parent.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [sys.executable, str(TRACKER_SCRIPT), "--daemon"],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif not any_live and _tracker_running():
        try:
            pid = int(TRACKER_PID.read_text().strip())
            os.kill(pid, signal_mod.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
        TRACKER_PID.unlink(missing_ok=True)


# ── Main ─────────────────────────────────────────────────────

def main():
    series_list = None
    scoreboard = None

    if requests is not None:
        # Fetch playoff series (may come from cache)
        try:
            series_list = fetch_playoff_series()
        except Exception:
            pass

        # Always fetch today's fresh scoreboard so we can patch stale
        # cache entries and track live bets with the same data.
        try:
            scoreboard = get_scoreboard()
        except Exception:
            pass

        # Patch cached series with real-time scores from the scoreboard
        if series_list and scoreboard:
            patch_series_with_live_data(series_list, scoreboard)

    # Section 1: NBA Playoffs
    print_playoff_section(series_list)

    # Load bets for sections 2 and 3
    try:
        bets, parlays = load_bets()
    except Exception:
        bets, parlays = [], []

    # If bets exist and scoreboard available, fetch live player stats
    game_stats = {}
    games = []
    if bets and scoreboard is not None:
        bet_teams = {espn_abbr(b["team"]) for b in bets if "team" in b}
        games = find_bet_games(scoreboard, bet_teams)
        for game in games:
            try:
                game_stats[game["event_id"]] = get_player_stats(game["event_id"])
            except Exception:
                pass

    # Section 2: Active Bets
    print_bets_section(bets, parlays, game_stats, games)

    # Section 3: Bankroll Status
    bankroll = load_bankroll()
    print_bankroll_section(bankroll)

    # Auto-start/stop live tracker daemon when bet games go live
    if games:
        try:
            manage_live_tracker(games)
        except Exception:
            pass  # never let process management break the dashboard


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort — never show an error in conky
        print("${color #00ff00}NBA Playoffs${color}")
        print("Dashboard unavailable")
