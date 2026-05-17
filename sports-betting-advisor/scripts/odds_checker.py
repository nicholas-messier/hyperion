#!/usr/bin/env python3
"""
DraftKings Odds Checker
Fetches current betting odds from DraftKings for NBA, NFL, MLB, and NHL.
Uses The Odds API (free tier: 500 requests/month).

Setup:
    1. Get a free API key at https://the-odds-api.com
    2. Set it as an environment variable:  export ODDS_API_KEY="your_key"
    3. Or pass it via --api-key flag

Usage:
    python3 odds_checker.py --sport nba
    python3 odds_checker.py --sport nfl
    python3 odds_checker.py --sport mlb
    python3 odds_checker.py --sport nhl
    python3 odds_checker.py --sport nba --market spreads
    python3 odds_checker.py --sport nfl --market player_props
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

ET_TZ = ZoneInfo("America/New_York")

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
}

MARKET_TYPES = {
    "h2h": "Moneyline (Head to Head)",
    "spreads": "Point Spreads",
    "totals": "Over/Under Totals",
}

BOOKMAKER = "draftkings"


def _load_dotenv() -> None:
    """Load .env file from the project root if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


def get_api_key(provided_key: Optional[str] = None) -> str:
    """Get the API key from argument, env var, .env file, or prompt."""
    _load_dotenv()
    key = provided_key or os.environ.get("ODDS_API_KEY")
    if not key:
        print("ERROR: No API key provided.")
        print("")
        print("To get a free API key (500 requests/month):")
        print("  1. Visit https://the-odds-api.com")
        print("  2. Sign up for a free account")
        print("  3. Copy your API key")
        print("")
        print("Then either:")
        print("  export ODDS_API_KEY='your_key'")
        print("  OR pass --api-key 'your_key'")
        sys.exit(1)
    return key


def fetch_odds(api_key: str, sport: str, markets: str = "h2h,spreads,totals") -> list:
    """Fetch odds from The Odds API for a given sport."""
    sport_key = SPORT_KEYS.get(sport.lower())
    if not sport_key:
        print(f"Unsupported sport: {sport}. Supported: {', '.join(SPORT_KEYS.keys())}")
        sys.exit(1)

    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": markets,
        "bookmakers": BOOKMAKER,
        "oddsFormat": "american",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code == 401:
            print("ERROR: Invalid API key. Check your ODDS_API_KEY.")
            sys.exit(1)
        elif resp.status_code == 429:
            print("ERROR: Rate limit exceeded. Free tier allows 500 requests/month.")
            sys.exit(1)

        resp.raise_for_status()

        # Show remaining requests
        remaining = resp.headers.get("x-requests-remaining", "?")
        used = resp.headers.get("x-requests-used", "?")
        print(f"  API Usage: {used} used / {remaining} remaining this month\n")

        return resp.json()

    except requests.RequestException as e:
        print(f"Error fetching odds: {e}")
        sys.exit(1)


def format_american_odds(odds: int) -> str:
    """Format American odds with + prefix for positive."""
    return f"+{odds}" if odds > 0 else str(odds)


def display_odds(games: list, sport: str):
    """Display odds in a formatted table."""
    if not games:
        print(f"  No {sport.upper()} games with DraftKings odds currently available.")
        print("  This usually means no games are scheduled soon.")
        return

    print(f"  Found {len(games)} upcoming {sport.upper()} game(s) on DraftKings:\n")

    for game in games:
        home = game.get("home_team", "Unknown")
        away = game.get("away_team", "Unknown")
        commence = game.get("commence_time", "")

        # Parse and format game time (API returns UTC; convert to ET for display)
        try:
            dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            dt_et = dt.astimezone(ET_TZ)
            game_time = dt_et.strftime("%a %b %d, %I:%M %p ET")
        except (ValueError, AttributeError):
            game_time = commence

        print(f"  {'='*60}")
        print(f"  {away} @ {home}")
        print(f"  {game_time}")
        print(f"  {'─'*60}")

        # Extract DraftKings odds
        dk_data = None
        for bookmaker in game.get("bookmakers", []):
            if bookmaker.get("key") == BOOKMAKER:
                dk_data = bookmaker
                break

        if not dk_data:
            print("  DraftKings odds not available for this game.\n")
            continue

        for market in dk_data.get("markets", []):
            market_key = market.get("key", "")
            market_label = MARKET_TYPES.get(market_key, market_key.upper())
            outcomes = market.get("outcomes", [])

            print(f"\n  {market_label}:")

            if market_key == "h2h":
                for outcome in outcomes:
                    name = outcome.get("name", "")
                    price = outcome.get("price", 0)
                    print(f"    {name:<25} {format_american_odds(price)}")

            elif market_key == "spreads":
                for outcome in outcomes:
                    name = outcome.get("name", "")
                    point = outcome.get("point", 0)
                    price = outcome.get("price", 0)
                    spread_str = f"+{point}" if point > 0 else str(point)
                    print(f"    {name:<25} {spread_str:<8} ({format_american_odds(price)})")

            elif market_key == "totals":
                for outcome in outcomes:
                    name = outcome.get("name", "")
                    point = outcome.get("point", 0)
                    price = outcome.get("price", 0)
                    print(f"    {name:<25} {point:<8} ({format_american_odds(price)})")

        print()


def fetch_player_props(api_key: str, sport: str) -> list:
    """Fetch player prop odds (requires paid tier on The Odds API)."""
    sport_key = SPORT_KEYS.get(sport.lower())
    if not sport_key:
        print(f"Unsupported sport: {sport}")
        sys.exit(1)

    # First get the list of available event IDs
    url = f"{ODDS_API_BASE}/sports/{sport_key}/events"
    params = {"apiKey": api_key}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()
    except requests.RequestException as e:
        print(f"Error fetching events: {e}")
        return []

    if not events:
        print(f"  No upcoming {sport.upper()} events found.")
        return []

    # Fetch player props for each event (note: may require paid API tier)
    all_props = []
    if sport.lower() == "mlb":
        prop_markets = "pitcher_strikeouts,batter_total_bases,batter_hits,batter_home_runs,batter_rbis,pitcher_outs"
    elif sport.lower() == "nfl":
        prop_markets = "player_pass_tds,player_rush_yds,player_reception_yds,player_points"
    elif sport.lower() == "nhl":
        prop_markets = "player_points,player_goals,player_assists,player_shots_on_goal,player_total_saves"
    else:
        # NBA defaults
        prop_markets = "player_points,player_rebounds,player_assists,player_threes"

    for event in events[:3]:  # Limit to first 3 events to save API calls
        event_id = event.get("id")
        props_url = f"{ODDS_API_BASE}/sports/{sport_key}/events/{event_id}/odds"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": prop_markets,
            "bookmakers": BOOKMAKER,
            "oddsFormat": "american",
        }

        try:
            resp = requests.get(props_url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    all_props.append(data)
        except requests.RequestException:
            continue

    return all_props


def display_player_props(props_data: list, sport: str):
    """Display player props in a formatted way."""
    if not props_data:
        print(f"\n  No player props available for {sport.upper()} on DraftKings.")
        print("  Note: Player props may require a paid API tier.")
        print("  Try --market h2h, spreads, or totals instead.")
        return

    for game_data in props_data:
        home = game_data.get("home_team", "Unknown")
        away = game_data.get("away_team", "Unknown")
        print(f"\n  {'='*60}")
        print(f"  Player Props: {away} @ {home}")
        print(f"  {'─'*60}")

        for bookmaker in game_data.get("bookmakers", []):
            if bookmaker.get("key") != BOOKMAKER:
                continue
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                print(f"\n  {market_key.replace('_', ' ').title()}:")
                for outcome in market.get("outcomes", []):
                    desc = outcome.get("description", "")
                    name = outcome.get("name", "")
                    point = outcome.get("point", "")
                    price = outcome.get("price", 0)
                    print(f"    {desc:<25} {name:<8} {point:<6} ({format_american_odds(price)})")


def main():
    parser = argparse.ArgumentParser(
        description="Check DraftKings odds across NBA, NFL, MLB, and NHL"
    )
    parser.add_argument(
        "--sport", required=True, choices=["nba", "nfl", "mlb", "nhl"],
        help="Sport to check (nba, nfl, mlb, or nhl)",
    )
    parser.add_argument(
        "--market", "-m", default="all",
        choices=["all", "h2h", "spreads", "totals", "player_props"],
        help="Market type to display. Default: all",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="The Odds API key (or set ODDS_API_KEY env var)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON response",
    )
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)

    print(f"\n{'='*60}")
    print(f"  DraftKings {args.sport.upper()} Odds")
    print(f"  Retrieved: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print(f"{'='*60}\n")

    if args.market == "player_props":
        props = fetch_player_props(api_key, args.sport)
        if args.json:
            print(json.dumps(props, indent=2))
        else:
            display_player_props(props, args.sport)
    else:
        markets = "h2h,spreads,totals" if args.market == "all" else args.market
        games = fetch_odds(api_key, args.sport, markets)

        if args.json:
            print(json.dumps(games, indent=2))
        else:
            display_odds(games, args.sport)


if __name__ == "__main__":
    main()
