#!/usr/bin/env python3
"""
NFL Player Stats Fetcher
Fetches individual NFL player stats from ESPN's free API.
No API key required.

Usage:
    python3 nfl_stats.py --player "Patrick Mahomes" --season 2024
    python3 nfl_stats.py --player "Derrick Henry" --season 2024 --last 5
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

import requests

# SQLite cache (optional — works without it)
try:
    from db import init_db as _init_db, cache_player_stats as _cache_stats, \
        get_cached_stats as _get_cached, get_cache_status as _get_cache_status
    _HAS_DB = True
except ImportError:
    _HAS_DB = False


ESPN_SEARCH_URL = "https://site.api.espn.com/apis/common/v3/search"
ESPN_GAMELOG_URL = (
    "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl"
    "/athletes/{player_id}/gamelog"
)
ESPN_PLAYER_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/football/nfl"
    "/athletes/{player_id}"
)


def search_player(name: str) -> Optional[dict]:
    """Search for an NFL player using ESPN's search API."""
    params = {"query": name, "limit": 10, "type": "player"}
    try:
        resp = requests.get(ESPN_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"Error searching for player: {e}")
        return None

    items = data.get("items", [])
    if not items:
        return None

    for item in items:
        display_name = item.get("displayName", "")
        player_id = item.get("id", "")
        if display_name and player_id:
            return {"name": display_name, "id": player_id}

    return None


def get_player_info(player_id: str) -> Optional[dict]:
    """Get player profile info from ESPN."""
    url = ESPN_PLAYER_URL.format(player_id=player_id)
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            athlete = data.get("athlete", data)
            return {
                "name": athlete.get("displayName", "Unknown"),
                "position": athlete.get("position", {}).get("abbreviation", "Unknown"),
                "team": athlete.get("team", {}).get("displayName", "Unknown"),
                "jersey": athlete.get("jersey", "?"),
                "age": athlete.get("age", "?"),
            }
    except requests.RequestException:
        pass
    return None


def get_player_gamelog(player_id: str, season: int) -> Optional[dict]:
    """Fetch a player's game log for a given NFL season from ESPN."""
    url = ESPN_GAMELOG_URL.format(player_id=player_id)
    params = {"season": season}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching game log: {e}")
        return None


def parse_gamelog(data: dict, last_n: Optional[int] = None) -> tuple:
    """Parse ESPN gamelog data into structured format.
    Returns (rows, season_type_labels).
    """
    season_types = data.get("seasonTypes", [])
    events = data.get("events", {})

    # Stat headers are in top-level 'labels', not inside categories
    raw_labels = data.get("labels", [])
    display_names = data.get("displayNames", [])

    # Handle duplicate labels (e.g., two 'YDS' for passing/rushing)
    # by appending a disambiguating suffix from displayNames
    stat_headers = []
    seen = {}
    for i, label in enumerate(raw_labels):
        if label in seen:
            # Use displayName to disambiguate
            if i < len(display_names):
                dn = display_names[i]
                if "Rush" in dn or "rush" in dn:
                    label = f"R_{label}"
                elif "Receiv" in dn or "Rec" in dn:
                    label = f"REC_{label}"
                elif "Pass" in dn or "pass" in dn:
                    label = f"P_{label}"
                else:
                    label = f"{label}{seen[label]}"
            else:
                label = f"{label}{seen[label]}"
            seen[label] = 1
        else:
            seen[label] = 2
        stat_headers.append(label)

    all_rows = []
    season_type_labels = []

    for st in season_types:
        st_name = st.get("displayName", "Unknown")
        categories = st.get("categories", [])

        for cat in categories:
            cat_events = cat.get("events", [])

            for ev in cat_events:
                event_id = ev.get("eventId", "")
                stats = ev.get("stats", [])

                # Get event metadata
                event_meta = events.get(event_id, {})
                opponent = event_meta.get("opponent", {})
                opp_name = opponent.get("abbreviation", "?")
                at_vs = event_meta.get("atVs", "vs")
                game_date = event_meta.get("gameDate", "")
                score = event_meta.get("score", "?")
                result = event_meta.get("gameResult", "?")
                week = event_meta.get("week", "?")

                # Format date
                try:
                    dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                    date_str = dt.strftime("%m/%d")
                except (ValueError, AttributeError):
                    date_str = "?"

                row = {
                    "WK": week,
                    "DATE": date_str,
                    "OPP": f"{at_vs} {opp_name}",
                    "RESULT": f"{result} {score}",
                }

                # Add stats
                for i, val in enumerate(stats):
                    if i < len(stat_headers):
                        row[stat_headers[i]] = val

                all_rows.append(row)
                season_type_labels.append(st_name)

    # Reverse to show chronological order (ESPN returns reverse chron)
    all_rows.reverse()
    season_type_labels.reverse()

    if last_n and last_n < len(all_rows):
        all_rows = all_rows[-last_n:]
        season_type_labels = season_type_labels[-last_n:]

    return all_rows, season_type_labels


def calculate_averages(rows: list) -> dict:
    """Calculate averages for numeric stat columns."""
    if not rows:
        return {}

    skip_cols = {"WK", "DATE", "OPP", "RESULT"}
    # Rate/percentage stats where total doesn't make sense — only show average
    rate_stats = {"CMP%", "AVG", "R_AVG", "REC_AVG", "P_AVG", "RTG", "QBR", "PCT"}
    numeric_totals = {}
    numeric_counts = {}

    for row in rows:
        for key, val in row.items():
            if key in skip_cols:
                continue
            try:
                num = float(val)
                numeric_totals[key] = numeric_totals.get(key, 0) + num
                numeric_counts[key] = numeric_counts.get(key, 0) + 1
            except (ValueError, TypeError):
                pass

    averages = {}
    for key in numeric_totals:
        count = numeric_counts[key]
        total = numeric_totals[key]
        is_rate = key in rate_stats
        averages[key] = {
            "total": round(total, 1),
            "avg": round(total / count, 1) if count > 0 else 0,
            "games": count,
            "is_rate": is_rate,
        }

    return averages


def format_table(rows: list, season_labels: list) -> str:
    """Format rows into a readable table."""
    if not rows:
        return "No games found."

    # Get all column headers
    all_keys = []
    for row in rows:
        for key in row.keys():
            if key not in all_keys:
                all_keys.append(key)

    # Calculate column widths
    widths = {}
    for key in all_keys:
        widths[key] = max(len(str(key)), max(len(str(row.get(key, ""))) for row in rows))

    # Build header
    header = "  ".join(str(key).rjust(widths[key]) for key in all_keys)
    separator = "  ".join("-" * widths[key] for key in all_keys)

    lines = [header, separator]

    prev_label = None
    for i, row in enumerate(rows):
        label = season_labels[i] if i < len(season_labels) else ""
        if label != prev_label and prev_label is not None:
            lines.append(f"  --- {label} ---")
        prev_label = label

        line = "  ".join(str(row.get(key, "")).rjust(widths[key]) for key in all_keys)
        lines.append(line)

    return "\n".join(lines)


def _display_nfl_stats(player_name, season, info, rows, season_labels, avgs, args):
    """Display formatted NFL stats output."""
    print(f"\n{'='*70}")
    print(f"  {player_name} - {season} NFL Season Stats")
    if info:
        print(f"  Position: {info.get('position', '?')} | Team: {info.get('team', '?')} | #{info.get('jersey', '?')}")
    print(f"{'='*70}\n")
    print(f"  Games: {len(rows)}\n")

    if avgs:
        print("  SEASON TOTALS / PER-GAME AVERAGES:")
        print(f"  {'─'*55}")

        for stat_key, vals in avgs.items():
            stat_display = stat_key.replace("_", " ")
            total = vals["total"]
            avg = vals["avg"]
            is_rate = vals.get("is_rate", False)
            if is_rate:
                avg_str = str(int(avg)) if avg == int(avg) else str(avg)
                print(f"    {stat_display:<20} Avg: {avg_str:>8}")
            else:
                total_str = str(int(total)) if total == int(total) else str(total)
                avg_str = str(int(avg)) if avg == int(avg) else str(avg)
                print(f"    {stat_display:<20} Total: {total_str:>8}  |  Per Game: {avg_str:>6}")

    if not args.averages_only:
        suffix = f" (Last {args.last} games)" if args.last else ""
        print(f"\n  GAME LOG{suffix}:")
        print(f"  {'─'*55}")
        print(format_table(rows, season_labels))

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch NFL player stats for a season (via ESPN)"
    )
    parser.add_argument(
        "--player", "-p", required=True, help="Player name (e.g., 'Patrick Mahomes')"
    )
    parser.add_argument(
        "--season", "-s", type=int, default=2024,
        help="Season year (e.g., 2024). Default: 2024",
    )
    parser.add_argument(
        "--last", "-l", type=int, default=None,
        help="Show only the last N games",
    )
    parser.add_argument(
        "--averages-only", "-a", action="store_true",
        help="Show only season averages",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Force a fresh API call, ignoring any cached data",
    )
    parser.add_argument(
        "--cache-status", action="store_true",
        help="Show cache status for this player and exit",
    )
    args = parser.parse_args()

    # Initialize DB cache if available
    if _HAS_DB:
        try:
            _init_db()
        except Exception:
            pass

    # Search for the player
    print(f"\nSearching for '{args.player}'...")
    player = search_player(args.player)

    if not player:
        print(f"Player '{args.player}' not found.")
        sys.exit(1)

    player_id = player["id"]
    player_name = player["name"]
    print(f"Found: {player_name} (ESPN ID: {player_id})")

    season_str = str(args.season)

    # --cache-status: show cache info and exit
    if args.cache_status:
        if not _HAS_DB:
            print("  Cache unavailable (db module not found)")
            sys.exit(0)
        status = _get_cache_status(player_name, "nfl", season_str)
        if status:
            fresh = "FRESH" if status["is_fresh"] else "STALE"
            print(f"\n  Cache status for {player_name} ({season_str}):")
            print(f"    Last fetched: {status['fetched_at']}")
            print(f"    Age: {status['age_hours']:.1f} hours ({fresh})")
            print(f"    Games cached: {status['games_played']}")
        else:
            print(f"\n  No cached data for {player_name} ({season_str})")
        sys.exit(0)

    # Try cache first (unless --refresh)
    if _HAS_DB and not args.refresh:
        try:
            cached = _get_cached(player_name, "nfl", season_str)
            if cached:
                print(f"  [Using cached data — {cached['fetched_at'][:16]}]")
                rows = cached["game_log_json"]
                avgs = cached["averages_json"]
                season_labels = ["Regular Season"] * len(rows)

                info = get_player_info(player_id)
                _display_nfl_stats(player_name, args.season, info, rows,
                                   season_labels, avgs, args)
                return
        except Exception:
            pass  # Cache miss or error — fetch from API

    # Get player info
    info = get_player_info(player_id)

    # Get game log
    print(f"Fetching {args.season} game log...")
    gamelog_data = get_player_gamelog(player_id, args.season)

    if not gamelog_data:
        print(f"No game log data found for {player_name} in {args.season}.")
        sys.exit(1)

    rows, season_labels = parse_gamelog(gamelog_data, args.last)

    if not rows:
        print(f"No games found for {player_name} in {args.season}.")
        print("The season may not have started yet or the player didn't play.")
        sys.exit(1)

    avgs = calculate_averages(rows)

    # Cache the results
    if _HAS_DB:
        try:
            _cache_stats(
                player_name=player_name,
                sport="nfl",
                season=season_str,
                game_log_json=rows,
                averages_json=avgs,
                games_played=len(rows),
            )
        except Exception:
            pass  # Cache write failed — non-fatal

    _display_nfl_stats(player_name, args.season, info, rows,
                       season_labels, avgs, args)


if __name__ == "__main__":
    main()
