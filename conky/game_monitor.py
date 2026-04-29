#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
game_monitor.py — Standalone live-tracker lifecycle manager.

Checks ESPN scoreboards for ALL 4 major sports (NBA, NFL, MLB, NHL)
for games involving teams with active bets.
Starts live_tracker.py --daemon when a bet game goes live, and stops it
when no tracked games remain in progress.

Designed to run from cron every few minutes as a fallback for when conky
is not running (the conky dashboard does the same check on its 60 s cycle).

Crontab entry:
    */3 * * * * /usr/bin/python3 /home/nmessier/bin/conky/game_monitor.py
"""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit(0)  # silently skip if requests not available

# Import shared sport config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "sports-betting-advisor" / "scripts"))
try:
    from sport_config import (
        get_all_scoreboard_urls, espn_abbr, detect_sport,
    )
except ImportError:
    # Fallback if sport_config not available
    def espn_abbr(team):
        return {"NYK": "NY", "SAS": "SA", "GSW": "GS", "NOP": "NO",
                "UTA": "UTAH"}.get(team, team)

    def get_all_scoreboard_urls():
        return {"nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"}

    def detect_sport(team, stat=""):
        return ""

BETS_FILE = Path.home() / ".config" / "sports-bets" / "active_bets.json"
TRACKER_SCRIPT = Path(__file__).resolve().parent.parent / "sports-betting-advisor" / "scripts" / "live_tracker.py"
TRACKER_PID = Path.home() / ".cache" / "sports-bets" / "live_tracker.pid"


def get_bet_teams():
    """Return set of ESPN team abbreviations that have active bets."""
    if not BETS_FILE.exists():
        return set()
    try:
        data = json.loads(BETS_FILE.read_text())
        return {espn_abbr(b.get("team", "")) for b in data.get("bets", []) if b.get("team")}
    except (json.JSONDecodeError, OSError):
        return set()


def any_game_live(bet_teams):
    """Check ESPN scoreboards for all sports for IN_PROGRESS games involving bet teams."""
    if not bet_teams:
        return False
    for sport, url in get_all_scoreboard_urls().items():
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            for event in resp.json().get("events", []):
                comp = event.get("competitions", [{}])[0]
                status = comp.get("status", {}).get("type", {}).get("name", "")
                if status not in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME",
                                  "STATUS_END_PERIOD"):
                    continue
                teams = {c.get("team", {}).get("abbreviation", "")
                         for c in comp.get("competitors", [])}
                if teams & bet_teams:
                    return True
        except Exception:
            pass
    return False


def tracker_running():
    """Check if the live tracker daemon is alive."""
    if not TRACKER_PID.exists():
        return False
    try:
        pid = int(TRACKER_PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        TRACKER_PID.unlink(missing_ok=True)
        return False


def start_tracker():
    """Start live_tracker.py in daemon mode."""
    TRACKER_PID.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [sys.executable, str(TRACKER_SCRIPT), "--daemon"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_tracker():
    """Send SIGTERM to the running live tracker daemon."""
    if not TRACKER_PID.exists():
        return
    try:
        pid = int(TRACKER_PID.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        pass
    TRACKER_PID.unlink(missing_ok=True)


def main():
    if not TRACKER_SCRIPT.exists():
        return

    bet_teams = get_bet_teams()
    if not bet_teams:
        if tracker_running():
            stop_tracker()
        return

    live = any_game_live(bet_teams)

    if live and not tracker_running():
        start_tracker()
    elif not live and tracker_running():
        stop_tracker()


if __name__ == "__main__":
    main()
