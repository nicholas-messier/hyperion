#!/usr/bin/env python3
"""
MLB Player Stats Fetcher
Fetches individual MLB player stats (batting + pitching) from ESPN's free API.
No API key required.

Usage:
    python3 mlb_stats.py --player "Aaron Judge" --season 2026
    python3 mlb_stats.py --player "Paul Skenes" --season 2026 --last 5
    python3 mlb_stats.py --player "Shohei Ohtani" --season 2026 --category batting
    python3 mlb_stats.py --player "Shohei Ohtani" --season 2026 --category pitching
"""

import argparse
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
    "https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb"
    "/athletes/{player_id}/gamelog"
)
ESPN_PLAYER_URL = (
    "https://site.api.espn.com/apis/common/v3/sports/baseball/mlb"
    "/athletes/{player_id}"
)

# Batting stats that benefit from per-game hit-rate analysis
BATTING_HIT_STATS = ["H", "HR", "RBI", "R", "SB", "BB", "SO", "2B", "3B"]
# Pitching stats that benefit from per-game hit-rate analysis
PITCHING_HIT_STATS = ["K", "IP", "ER", "BB", "H"]
# Rate stats — show as average only, not totals
RATE_STATS = {"AVG", "OBP", "SLG", "OPS", "ERA"}


def search_player(name: str) -> Optional[dict]:
    """Search for an MLB player using ESPN's search API."""
    params = {"query": name, "limit": 10, "type": "player"}
    try:
        resp = requests.get(ESPN_SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"Error searching for player: {e}")
        return None

    items = data.get("items", [])
    # Prefer MLB players if multiple sports match the name
    mlb_first = sorted(
        items, key=lambda it: 0 if it.get("defaultLeagueSlug") == "mlb" else 1
    )
    for item in mlb_first:
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
                "bats": athlete.get("bats", {}).get("abbreviation", "?"),
                "throws": athlete.get("throws", {}).get("abbreviation", "?"),
            }
    except requests.RequestException:
        pass
    return None


def get_player_gamelog(player_id: str, season: int,
                       category: Optional[str] = None) -> Optional[dict]:
    """Fetch a player's game log for a given MLB season from ESPN.

    category: 'batting' or 'pitching'. None = use player's default.
    """
    url = ESPN_GAMELOG_URL.format(player_id=player_id)
    params = {"season": season}
    if category:
        params["category"] = category

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching game log: {e}")
        return None


def detect_category(data: dict) -> str:
    """Detect whether the returned gamelog is batting or pitching, and
    whether the player has both available (two-way)."""
    filters = data.get("filters", [])
    for f in filters:
        if f.get("name") == "category":
            return f.get("value", "batting")
    # Fallback: infer from labels
    labels = data.get("labels", [])
    return "pitching" if "IP" in labels else "batting"


def available_categories(data: dict) -> list:
    """List of categories ESPN offers for this player (batting / pitching / both)."""
    filters = data.get("filters", [])
    for f in filters:
        if f.get("name") == "category":
            return [opt["value"] for opt in f.get("options", [])]
    return []


def parse_gamelog(data: dict, last_n: Optional[int] = None) -> tuple:
    """Parse ESPN MLB gamelog data.

    MLB gamelog categories within seasonTypes are months (april/may/...),
    not flat. We flatten + sort by gameDate.

    Returns (rows, category).
    """
    labels = data.get("labels", [])
    events_meta = data.get("events", {})
    season_types = data.get("seasonTypes", [])

    rows = []
    for st in season_types:
        st_name = st.get("displayName", "Regular Season")
        for cat in st.get("categories", []):
            for ev in cat.get("events", []):
                event_id = ev.get("eventId", "")
                stats = ev.get("stats", [])
                meta = events_meta.get(event_id, {})

                opponent = meta.get("opponent", {})
                opp_abbr = opponent.get("abbreviation", "?")
                at_vs = meta.get("atVs", "vs")
                game_date = meta.get("gameDate", "")
                score = meta.get("score", "?")
                result = meta.get("gameResult", "?")

                try:
                    dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                    date_str = dt.strftime("%m/%d")
                    date_sort = dt.timestamp()
                except (ValueError, AttributeError):
                    date_str = "?"
                    date_sort = 0

                row = {
                    "DATE": date_str,
                    "_sort": date_sort,
                    "OPP": f"{at_vs} {opp_abbr}",
                    "RESULT": f"{result} {score}",
                    "_season_type": st_name,
                }
                for i, val in enumerate(stats):
                    if i < len(labels):
                        row[labels[i]] = val
                rows.append(row)

    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        r.pop("_sort", None)

    if last_n and last_n < len(rows):
        rows = rows[-last_n:]

    return rows, labels


def safe_float(val) -> Optional[float]:
    """Convert MLB stat strings to floats. Handles '.267', '5.1' (innings), etc."""
    if val is None or val == "" or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def innings_to_outs(ip_str) -> Optional[int]:
    """Convert MLB innings notation (e.g. '5.2' = 5 ip + 2 outs = 17 outs)
    into total outs. Returns None if unparseable."""
    if ip_str is None or ip_str == "":
        return None
    try:
        s = str(ip_str)
        if "." in s:
            whole, frac = s.split(".")
            return int(whole) * 3 + int(frac)
        return int(s) * 3
    except (ValueError, TypeError):
        return None


def calculate_averages(rows: list, labels: list) -> dict:
    """Calculate per-game averages and season totals for MLB stats.

    Special handling:
      - IP: aggregated via outs, then converted back to innings notation
      - Rate stats (AVG/OBP/SLG/OPS/ERA): show most-recent (last game) value
    """
    if not rows:
        return {}

    averages = {}
    for label in labels:
        if label == "IP":
            # Sum outs, convert back
            total_outs = 0
            n = 0
            for r in rows:
                outs = innings_to_outs(r.get(label))
                if outs is not None:
                    total_outs += outs
                    n += 1
            if n:
                total_ip = f"{total_outs // 3}.{total_outs % 3}"
                # Per-game IP as float for display
                per_game = round(total_outs / 3 / n, 2)
                averages[label] = {
                    "total": total_ip, "avg": per_game,
                    "games": n, "is_rate": False,
                }
            continue

        if label in RATE_STATS:
            # For rate stats, the LAST row is the running season figure
            for r in reversed(rows):
                v = safe_float(r.get(label))
                if v is not None:
                    averages[label] = {
                        "total": None, "avg": v, "games": len(rows), "is_rate": True,
                    }
                    break
            continue

        # Normal counting stats — sum and average
        total, n = 0.0, 0
        for r in rows:
            v = safe_float(r.get(label))
            if v is not None:
                total += v
                n += 1
        if n:
            averages[label] = {
                "total": round(total, 1),
                "avg": round(total / n, 2),
                "games": n,
                "is_rate": False,
            }
    return averages


def calculate_hit_rates(rows: list, category: str) -> dict:
    """Calculate hit rates for common prop targets over the last 5 / 10 games.

    For each interesting stat, returns:
      { 'L5': {target: hit_count}, 'L10': {target: hit_count} }
    """
    stats_to_check = BATTING_HIT_STATS if category == "batting" else PITCHING_HIT_STATS
    last5 = rows[-5:]
    last10 = rows[-10:]

    result = {}
    for stat in stats_to_check:
        # Skip stats not in this row's data
        if not any(stat in r for r in rows):
            continue

        # Common prop targets to evaluate
        if stat == "HR":
            targets = [0.5, 1.5]  # Over 0.5 HR (= "hits a HR")
        elif stat == "RBI":
            targets = [0.5, 1.5, 2.5]
        elif stat == "R":
            targets = [0.5, 1.5]
        elif stat == "SB":
            targets = [0.5]
        elif stat == "K":  # strikeouts thrown (pitcher)
            targets = [4.5, 5.5, 6.5, 7.5]
        elif stat == "IP":
            targets = [4.5, 5.5, 6.5]
        elif stat == "ER":
            targets = [1.5, 2.5, 3.5]
        elif stat == "H":
            # For pitchers H = hits allowed, batters H = hits got
            if category == "batting":
                targets = [0.5, 1.5, 2.5]
            else:
                targets = [4.5, 5.5, 6.5]
        elif stat == "BB":
            if category == "batting":
                targets = [0.5]
            else:
                targets = [1.5, 2.5]
        elif stat == "SO":  # batter strikeouts (avoid)
            targets = [1.5]
        else:
            targets = [0.5, 1.5]

        for target in targets:
            l5_hits = sum(
                1 for r in last5
                if (v := safe_float(r.get(stat))) is not None and v > target
            )
            l10_hits = sum(
                1 for r in last10
                if (v := safe_float(r.get(stat))) is not None and v > target
            )
            l5_games = sum(1 for r in last5 if r.get(stat) not in (None, ""))
            l10_games = sum(1 for r in last10 if r.get(stat) not in (None, ""))
            key = f"{stat} O{target}"
            result[key] = {
                "L5": f"{l5_hits}/{l5_games}",
                "L10": f"{l10_hits}/{l10_games}",
                "L5_pct": round(100 * l5_hits / l5_games, 1) if l5_games else 0,
                "L10_pct": round(100 * l10_hits / l10_games, 1) if l10_games else 0,
            }
    return result


def format_table(rows: list, labels: list) -> str:
    """Format rows into a readable table."""
    if not rows:
        return "No games found."

    display_cols = ["DATE", "OPP", "RESULT"] + labels
    widths = {}
    for col in display_cols:
        widths[col] = max(
            len(str(col)),
            max(len(str(r.get(col, ""))) for r in rows),
        )

    header = "  ".join(str(c).rjust(widths[c]) for c in display_cols)
    sep = "  ".join("-" * widths[c] for c in display_cols)
    lines = [header, sep]
    for r in rows:
        lines.append(
            "  ".join(str(r.get(c, "")).rjust(widths[c]) for c in display_cols)
        )
    return "\n".join(lines)


def _display_mlb_stats(player_name, season, info, rows, labels, avgs,
                       hit_rates, category, args):
    """Display formatted MLB stats output."""
    print(f"\n{'='*70}")
    print(f"  {player_name} - {season} MLB Season Stats ({category.upper()})")
    if info:
        print(f"  Position: {info.get('position', '?')} | "
              f"Team: {info.get('team', '?')} | #{info.get('jersey', '?')} | "
              f"B/T: {info.get('bats', '?')}/{info.get('throws', '?')}")
    print(f"{'='*70}\n")
    print(f"  Games in log: {len(rows)}\n")

    if avgs:
        print(f"  SEASON {category.upper()} LINE (per-game / totals):")
        print(f"  {'─'*55}")
        for stat in labels:
            if stat not in avgs:
                continue
            v = avgs[stat]
            is_rate = v.get("is_rate", False)
            if is_rate:
                avg_str = f"{v['avg']:.3f}".lstrip("0") if v['avg'] < 1 else f"{v['avg']:.2f}"
                print(f"    {stat:<6} Season: {avg_str:>8}")
            elif v["total"] is None:
                print(f"    {stat:<6} {'-':>8}")
            else:
                total = v["total"]
                avg = v["avg"]
                print(f"    {stat:<6} Total: {str(total):>6}  |  Per Game: {avg:>6}")

    if hit_rates:
        print(f"\n  PROP HIT RATES (Last 5 / Last 10):")
        print(f"  {'─'*55}")
        for prop, vals in hit_rates.items():
            l5 = vals["L5"]
            l10 = vals["L10"]
            l5p = vals["L5_pct"]
            l10p = vals["L10_pct"]
            print(f"    {prop:<14}  L5: {l5:>5} ({l5p:>5.1f}%)   "
                  f"L10: {l10:>5} ({l10p:>5.1f}%)")

    if not args.averages_only:
        suffix = f" (Last {args.last} games)" if args.last else ""
        print(f"\n  GAME LOG{suffix}:")
        print(f"  {'─'*55}")
        print(format_table(rows, labels))
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch MLB player stats for a season (via ESPN)"
    )
    parser.add_argument("--player", "-p", required=True,
                        help="Player name (e.g., 'Aaron Judge')")
    parser.add_argument("--season", "-s", type=int, default=2026,
                        help="Season year (e.g., 2026). Default: 2026")
    parser.add_argument("--last", "-l", type=int, default=None,
                        help="Show only the last N games")
    parser.add_argument("--category", "-c", default=None,
                        choices=["batting", "pitching"],
                        help="Force batting or pitching (for two-way players)")
    parser.add_argument("--averages-only", "-a", action="store_true",
                        help="Show only season averages + hit rates (no game log)")
    parser.add_argument("--refresh", action="store_true",
                        help="Force a fresh API call, ignoring any cached data")
    parser.add_argument("--cache-status", action="store_true",
                        help="Show cache status for this player and exit")
    args = parser.parse_args()

    if _HAS_DB:
        try:
            _init_db()
        except Exception:
            pass

    print(f"\nSearching for '{args.player}'...")
    player = search_player(args.player)
    if not player:
        print(f"Player '{args.player}' not found.")
        sys.exit(1)

    player_id = player["id"]
    player_name = player["name"]
    print(f"Found: {player_name} (ESPN ID: {player_id})")

    season_str = str(args.season)
    # Cache key includes category to avoid two-way player collision
    cache_category = args.category or "auto"
    cache_sport = f"mlb_{cache_category}"

    if args.cache_status:
        if not _HAS_DB:
            print("  Cache unavailable (db module not found)")
            sys.exit(0)
        # Check both batting + pitching caches
        for cat in ["mlb_batting", "mlb_pitching", "mlb_auto"]:
            status = _get_cache_status(player_name, cat, season_str)
            if status:
                fresh = "FRESH" if status["is_fresh"] else "STALE"
                print(f"\n  Cache [{cat}] for {player_name} ({season_str}):")
                print(f"    Last fetched: {status['fetched_at']}")
                print(f"    Age: {status['age_hours']:.1f} hours ({fresh})")
                print(f"    Games cached: {status['games_played']}")
        sys.exit(0)

    # Try cache first
    if _HAS_DB and not args.refresh:
        try:
            cached = _get_cached(player_name, cache_sport, season_str)
            if cached:
                print(f"  [Using cached data — {cached['fetched_at'][:16]}]")
                rows = cached["game_log_json"]
                avgs = cached["averages_json"]
                # Reconstruct labels from rows (use first row's stat-ish keys)
                meta_cols = {"DATE", "OPP", "RESULT", "_season_type"}
                labels = [k for k in rows[0].keys() if k not in meta_cols] \
                    if rows else []
                detected_cat = "pitching" if "IP" in labels else "batting"
                hit_rates = calculate_hit_rates(rows, detected_cat)
                info = get_player_info(player_id)
                _display_mlb_stats(player_name, args.season, info, rows,
                                   labels, avgs, hit_rates, detected_cat, args)
                return
        except Exception:
            pass

    info = get_player_info(player_id)

    print(f"Fetching {args.season} game log...")
    gamelog_data = get_player_gamelog(player_id, args.season,
                                      category=args.category)
    if not gamelog_data:
        print(f"No game log data found for {player_name} in {args.season}.")
        sys.exit(1)

    available = available_categories(gamelog_data)
    detected_cat = detect_category(gamelog_data)

    rows, labels = parse_gamelog(gamelog_data, args.last)
    if not rows:
        print(f"No games found for {player_name} in {args.season} ({detected_cat}).")
        if "batting" in available and "pitching" in available:
            print("Note: this is a two-way player. Try --category batting or "
                  "--category pitching.")
        sys.exit(1)

    avgs = calculate_averages(rows, labels)
    hit_rates = calculate_hit_rates(rows, detected_cat)

    if _HAS_DB:
        try:
            _cache_stats(
                player_name=player_name,
                sport=cache_sport,
                season=season_str,
                game_log_json=rows,
                averages_json=avgs,
                games_played=len(rows),
            )
        except Exception:
            pass

    _display_mlb_stats(player_name, args.season, info, rows, labels, avgs,
                       hit_rates, detected_cat, args)

    # Only show two-way note if the OTHER category has REAL game data.
    # ESPN lists both options for everyone, but pitchers get phantom batting
    # "events" with all-zero stats for interleague games where they appeared
    # but didn't bat. Filter to events with actual activity (AB>0 for batting,
    # IP>0 for pitching).
    if len(available) > 1 and not args.category:
        other = [c for c in available if c != detected_cat]
        if other:
            other_data = get_player_gamelog(player_id, args.season,
                                            category=other[0])
            if other_data:
                other_labels = other_data.get("labels", [])
                activity_stat = "AB" if other[0] == "batting" else "IP"
                idx = other_labels.index(activity_stat) \
                    if activity_stat in other_labels else -1
                real_events = 0
                if idx >= 0:
                    for st in other_data.get("seasonTypes", []):
                        for c in st.get("categories", []):
                            for ev in c.get("events", []):
                                stats = ev.get("stats", [])
                                if idx < len(stats):
                                    v = safe_float(stats[idx])
                                    if v and v > 0:
                                        real_events += 1
                if real_events >= 5:
                    print(f"\n  NOTE: {player_name} is two-way. "
                          f"Currently showing {detected_cat}.")
                    print(f"  Run with --category {other[0]} to see the "
                          f"other side ({real_events} games).")


if __name__ == "__main__":
    main()
