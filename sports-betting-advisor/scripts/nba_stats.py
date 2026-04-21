#!/usr/bin/env python3
"""
NBA Player Stats Fetcher
Fetches individual player stats across multiple games in a single season.
Uses the free nba_api package (no API key required).

Usage:
    python3 nba_stats.py --player "LeBron James" --season 2024
    python3 nba_stats.py --player "Stephen Curry" --season 2024 --last 10
"""

import argparse
import json
import sys
from typing import Optional

import pandas as pd
from nba_api.stats.endpoints import (
    commonplayerinfo,
    playergamelog,
    playercareerstats,
)
from nba_api.stats.static import players

# SQLite cache (optional — works without it)
try:
    from db import init_db as _init_db, cache_player_stats as _cache_stats, \
        get_cached_stats as _get_cached, get_cache_status as _get_cache_status
    _HAS_DB = True
except ImportError:
    _HAS_DB = False


def find_player(name: str) -> Optional[dict]:
    """Search for a player by name. Returns the best match."""
    matches = players.find_players_by_full_name(name)
    if not matches:
        # Try partial match
        parts = name.lower().split()
        all_players = players.get_players()
        for p in all_players:
            full = f"{p['first_name']} {p['last_name']}".lower()
            if all(part in full for part in parts):
                matches.append(p)
    if not matches:
        return None
    # Prefer active players
    active = [p for p in matches if p.get("is_active", False)]
    return active[0] if active else matches[0]


def get_season_string(year: int) -> str:
    """Convert a year to NBA season string format (e.g., 2024 -> '2024-25')."""
    next_year = str(year + 1)[-2:]
    return f"{year}-{next_year}"


def get_player_game_log(player_id: int, season: str) -> pd.DataFrame:
    """Fetch a player's game log for a given season."""
    log = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=season,
        season_type_all_star="Regular Season",
    )
    df = log.get_data_frames()[0]
    return df


def get_player_career_stats(player_id: int) -> pd.DataFrame:
    """Fetch a player's career stats."""
    career = playercareerstats.PlayerCareerStats(player_id=player_id)
    df = career.get_data_frames()[0]
    return df


def format_game_log(df: pd.DataFrame, last_n: Optional[int] = None) -> str:
    """Format game log data into a readable table."""
    if df.empty:
        return "No games found for this season."

    cols = [
        "GAME_DATE", "MATCHUP", "WL", "MIN", "PTS", "REB", "AST",
        "STL", "BLK", "TOV", "FGM", "FGA", "FG_PCT",
        "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "PLUS_MINUS",
    ]
    available_cols = [c for c in cols if c in df.columns]
    display_df = df[available_cols].copy()

    if last_n and last_n < len(display_df):
        display_df = display_df.head(last_n)

    # Format percentages
    for pct_col in ["FG_PCT", "FG3_PCT", "FT_PCT"]:
        if pct_col in display_df.columns:
            display_df[pct_col] = display_df[pct_col].apply(
                lambda x: f"{x:.1%}" if pd.notna(x) else "N/A"
            )

    return display_df.to_string(index=False)


def calculate_averages(df: pd.DataFrame) -> dict:
    """Calculate season averages from game log."""
    if df.empty:
        return {}

    stat_cols = [
        "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
        "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "PLUS_MINUS",
    ]
    avgs = {}
    for col in stat_cols:
        if col in df.columns:
            numeric = pd.to_numeric(df[col], errors="coerce")
            avgs[col] = round(numeric.mean(), 1)

    # Calculate percentages from totals
    if "FGM" in df.columns and "FGA" in df.columns:
        total_fgm = pd.to_numeric(df["FGM"], errors="coerce").sum()
        total_fga = pd.to_numeric(df["FGA"], errors="coerce").sum()
        avgs["FG_PCT"] = f"{total_fgm / total_fga:.1%}" if total_fga > 0 else "N/A"

    if "FG3M" in df.columns and "FG3A" in df.columns:
        total_fg3m = pd.to_numeric(df["FG3M"], errors="coerce").sum()
        total_fg3a = pd.to_numeric(df["FG3A"], errors="coerce").sum()
        avgs["FG3_PCT"] = f"{total_fg3m / total_fg3a:.1%}" if total_fg3a > 0 else "N/A"

    if "FTM" in df.columns and "FTA" in df.columns:
        total_ftm = pd.to_numeric(df["FTM"], errors="coerce").sum()
        total_fta = pd.to_numeric(df["FTA"], errors="coerce").sum()
        avgs["FT_PCT"] = f"{total_ftm / total_fta:.1%}" if total_fta > 0 else "N/A"

    return avgs


def _display_stats(player_name, season_str, game_log, avgs, args):
    """Display formatted stats output."""
    games_played = len(game_log) if hasattr(game_log, '__len__') else 0

    print(f"\n{'='*70}")
    print(f"  {player_name} - {season_str} Season Stats")
    print(f"{'='*70}\n")

    print(f"  Games Played: {games_played}\n")

    # Show season averages
    print("  SEASON AVERAGES:")
    print(f"  {'─'*50}")
    core_stats = {
        "PTS": "Points", "REB": "Rebounds", "AST": "Assists",
        "STL": "Steals", "BLK": "Blocks", "TOV": "Turnovers",
        "MIN": "Minutes", "PLUS_MINUS": "+/-",
    }
    for key, label in core_stats.items():
        if key in avgs:
            print(f"    {label:.<20} {avgs[key]}")

    shooting = {"FG_PCT": "FG%", "FG3_PCT": "3PT%", "FT_PCT": "FT%"}
    print(f"\n  SHOOTING SPLITS:")
    print(f"  {'─'*50}")
    for key, label in shooting.items():
        if key in avgs:
            print(f"    {label:.<20} {avgs[key]}")
        elif key.replace("_PCT", "M") in avgs:
            made_key = key.replace("_PCT", "M")
            att_key = key.replace("_PCT", "A")
            print(f"    {label:.<20} {avgs.get(made_key, 0)}/{avgs.get(att_key, 0)}")

    if not args.averages_only and hasattr(game_log, 'to_string'):
        print(f"\n  GAME LOG{'(Last ' + str(args.last) + ' games)' if args.last else ''}:")
        print(f"  {'─'*50}")
        print(format_game_log(game_log, args.last))

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch NBA player stats for a season"
    )
    parser.add_argument(
        "--player", "-p", required=True, help="Player name (e.g., 'LeBron James')"
    )
    parser.add_argument(
        "--season", "-s", type=int, default=2024,
        help="Season year (e.g., 2024 for the 2024-25 season). Default: 2024",
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

    # Find the player
    player = find_player(args.player)
    if not player:
        print(f"Player '{args.player}' not found.")
        sys.exit(1)

    player_name = f"{player['first_name']} {player['last_name']}"
    player_id = player["id"]
    season_str = get_season_string(args.season)

    # Initialize DB cache if available
    if _HAS_DB:
        try:
            _init_db()
        except Exception:
            pass

    # --cache-status: show cache info and exit
    if args.cache_status:
        if not _HAS_DB:
            print("  Cache unavailable (db module not found)")
            sys.exit(0)
        status = _get_cache_status(player_name, "nba", season_str)
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
            cached = _get_cached(player_name, "nba", season_str)
            if cached:
                print(f"  [Using cached data — {cached['fetched_at'][:16]}]")
                game_log_records = cached["game_log_json"]
                avgs = cached["averages_json"]

                # Reconstruct DataFrame for game log display
                if game_log_records:
                    game_log = pd.DataFrame(game_log_records)
                else:
                    game_log = pd.DataFrame()

                _display_stats(player_name, season_str, game_log, avgs, args)
                return
        except Exception:
            pass  # Cache miss or error — fetch from API

    # Fetch from API
    try:
        game_log = get_player_game_log(player_id, season_str)
    except Exception as e:
        print(f"Error fetching game log: {e}")
        sys.exit(1)

    if game_log.empty:
        print(f"No games found for {player_name} in the {season_str} season.")
        sys.exit(0)

    avgs = calculate_averages(game_log)

    # Cache the results
    if _HAS_DB:
        try:
            game_log_records = json.loads(game_log.to_json(orient="records",
                                                            date_format="iso"))
            _cache_stats(
                player_name=player_name,
                sport="nba",
                season=season_str,
                game_log_json=game_log_records,
                averages_json=avgs,
                games_played=len(game_log),
            )
        except Exception:
            pass  # Cache write failed — non-fatal

    _display_stats(player_name, season_str, game_log, avgs, args)


if __name__ == "__main__":
    main()
