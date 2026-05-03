#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Auto-Settle — Automatically settle active bets when games go final.

Checks ESPN box scores for final game stats, compares against active bets
in the SQLite database, and settles them (W/L) with proper payout calculation
from stored odds.

Usage:
    # One-shot: settle any bets whose games are final, then exit
    python3 scripts/auto_settle.py

    # Watch mode: keep checking every N seconds until all bets are settled
    python3 scripts/auto_settle.py --watch --interval 60

    # Dry run: show what would be settled without making changes
    python3 scripts/auto_settle.py --dry-run

    # Cron-friendly (no output unless something was settled)
    python3 scripts/auto_settle.py --quiet
"""

import argparse
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Add scripts dir to path so we can import db
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import (
    init_db,
    get_active_bets,
    settle_bet,
    settle_parlay,
    sync_json,
)

# ── Sport config ─────────────────────────────────────────────

from sport_config import (
    SPORTS, espn_abbr, dk_abbr, get_sport_urls,
    get_all_scoreboard_urls, detect_sport,
    extract_player_stats_from_summary, get_stat_value,
    check_moneyline, check_spread,
)


# ── Payout math ──────────────────────────────────────────────

def calc_payout(wager: float, odds: int) -> float:
    """Calculate total payout (wager + profit) from American odds.

    DraftKings floors profit to 2 decimal places rather than rounding,
    so we use math.floor to match their payouts exactly.

    Returns 0 if odds are missing/zero (can't calculate).
    """
    if not odds:
        return 0.0
    if odds < 0:
        # e.g., -151 -> profit = wager * (100 / 151)
        profit = wager * (100 / abs(odds))
    else:
        # e.g., +228 -> profit = wager * (228 / 100)
        profit = wager * (odds / 100)
    # DK floors profit to the cent
    profit = math.floor(profit * 100) / 100
    return round(wager + profit, 2)


# ── ESPN data fetching ───────────────────────────────────────

def fetch_all_scoreboards() -> dict:
    """Fetch today's scoreboards for all sports.

    Returns {sport_key: scoreboard_json}.
    """
    scoreboards = {}
    for sport, url in get_all_scoreboard_urls().items():
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            scoreboards[sport] = resp.json()
        except requests.RequestException:
            pass
    return scoreboards


def fetch_box_score(event_id: str, sport: str = "nba") -> dict:
    """Fetch full game summary/box score from ESPN."""
    _, summary_url = get_sport_urls(sport)
    resp = requests.get(summary_url, params={"event": event_id}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_final_games(scoreboards: dict) -> dict:
    """Extract final games from all scoreboards.

    Returns {team_abbr: [event_info, ...]} mapping every team in a final
    game to a list of that team's final games. Multiple entries per team
    is possible when the scoreboard returns games from multiple days
    (e.g., yesterday's final + today's final). Each event_info includes
    the game's UTC date so callers can ensure they only match a bet to
    a game that occurred on/after the bet's placed_at date.
    """
    finals = {}
    for sport, scoreboard in scoreboards.items():
        for event in scoreboard.get("events", []):
            comp = event.get("competitions", [{}])[0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue
            competitors = comp.get("competitors", [])
            teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
            info = {
                "event_id": event["id"],
                "name": event.get("name", ""),
                "teams": teams,
                "status": status,
                "sport": sport,
                "date": event.get("date", ""),  # ISO 8601 UTC, e.g. 2026-05-02T23:30Z
            }
            for t in teams:
                finals.setdefault(t, []).append(info)
    return finals


def find_final_game_for_bet(
    final_games: dict,
    team: str,
    placed_at: str,
    sport: str = "",
) -> dict | None:
    """Find the final game for `team` that this bet should settle against.

    Returns the most recent final game that satisfies BOTH:
        1. Sport matches the bet's sport (if provided). Prevents an NBA
           Celtics bet from matching an MLB Red Sox final with the same
           "BOS" abbreviation.
        2. Game's UTC date is on or after the bet's placed_at date.
           Prevents a bet placed today from matching yesterday's stale
           STATUS_FINAL game still on the scoreboard window. (This is
           the bug we hit on May 2 2026 — a Game 7 spread bet matched
           Game 6 from two days earlier.)

    Returns None if no matching game is found.
    """
    games = final_games.get(team, [])
    if not games:
        return None

    # Determine the earliest-acceptable game date from the bet's placed_at.
    # We treat both as UTC-comparable strings; ISO 8601 sorts lexically.
    # Trim placed_at to YYYY-MM-DD so a 12:18 PM bet placement still
    # accepts a 7:30 PM game (same calendar day in local time, even if
    # the game's UTC stamp rolls over to the next UTC date).
    bet_day = (placed_at or "")[:10]
    if not bet_day:
        # No placed_at — safest is to skip rather than silently match.
        return None

    # Sport-filter first (drops cross-sport collisions like NBA BOS vs MLB BOS)
    if sport:
        games = [g for g in games if g.get("sport") == sport]
        if not games:
            return None

    # Sort newest-first; pick the first game on/after bet_day
    sorted_games = sorted(games, key=lambda g: g.get("date", ""), reverse=True)
    for g in sorted_games:
        game_day = (g.get("date") or "")[:10]
        if game_day and game_day >= bet_day:
            return g
    return None


def get_in_progress_games(scoreboards: dict) -> dict:
    """Extract in-progress games from all scoreboards.

    Returns {team_abbr: event_info} for games currently being played.
    """
    in_progress = {}
    for sport, scoreboard in scoreboards.items():
        for event in scoreboard.get("events", []):
            comp = event.get("competitions", [{}])[0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status not in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME",
                              "STATUS_END_PERIOD"):
                continue
            competitors = comp.get("competitors", [])
            teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
            detail = comp.get("status", {}).get("type", {}).get("shortDetail", "")
            info = {
                "event_id": event["id"],
                "name": event.get("name", ""),
                "teams": teams,
                "status": status,
                "detail": detail,
                "sport": sport,
            }
            for t in teams:
                in_progress[t] = info
    return in_progress


# ── Settlement logic ─────────────────────────────────────────

def settle_active_bets(dry_run: bool = False, quiet: bool = False) -> dict:
    """Check all active bets against final game stats and settle them.

    Returns a summary dict: {settled: int, wins: int, losses: int,
                             pending: int, errors: list}.
    """
    init_db()
    bets, parlays = get_active_bets()

    if not bets:
        if not quiet:
            print("No active bets to settle.")
        return {"settled": 0, "wins": 0, "losses": 0, "pending": 0, "errors": []}

    # Fetch scoreboards for all sports
    try:
        scoreboards = fetch_all_scoreboards()
    except Exception as e:
        msg = f"Failed to fetch scoreboards: {e}"
        if not quiet:
            print(f"ERROR: {msg}")
        return {"settled": 0, "wins": 0, "losses": 0,
                "pending": len(bets), "errors": [msg]}

    if not scoreboards:
        msg = "No scoreboards available"
        if not quiet:
            print(f"ERROR: {msg}")
        return {"settled": 0, "wins": 0, "losses": 0,
                "pending": len(bets), "errors": [msg]}

    final_games = get_final_games(scoreboards)
    in_progress = get_in_progress_games(scoreboards)

    # Resolve each bet to its specific final game (or None) using the
    # placed_at date guard. Storing this per-bet (instead of per-team)
    # is what prevents the bug where a bet placed today gets matched
    # against yesterday's final game still on the scoreboard.
    bet_games = {}  # bet_id -> resolved final game info, or None
    parlay_map = {}
    bet_parlay_legs = {}

    for p in parlays:
        parlay_map[p["id"]] = p

    for bet in bets:
        team = espn_abbr(bet.get("team", ""))
        placed_at = bet.get("placed_at", "")
        # Sport guard prevents cross-sport team-abbr collisions
        # (e.g., NBA Celtics "BOS" matching MLB Red Sox "BOS").
        bet_sport = bet.get("sport", "") or detect_sport(team, bet.get("stat", ""))
        bet_games[bet["id"]] = find_final_game_for_bet(
            final_games, team, placed_at, sport=bet_sport,
        )
        if bet.get("parlay_id"):
            bet_parlay_legs.setdefault(bet["parlay_id"], []).append(bet)

    # Fetch box scores for the resolved games (one fetch per unique event)
    game_stats = {}  # event_id -> player_stats
    fetched_events = set()

    for bet in bets:
        game = bet_games.get(bet["id"])
        if not game:
            continue
        event_id = game["event_id"]
        if event_id in fetched_events:
            continue
        fetched_events.add(event_id)
        sport = game.get("sport", "nba")
        try:
            summary = fetch_box_score(event_id, sport=sport)
            game_stats[event_id] = extract_player_stats_from_summary(summary, sport=sport)
        except requests.RequestException as e:
            if not quiet:
                print(f"  Warning: Could not fetch box score for {game['name']}: {e}")

    # Merge all player stats into one dict (players are unique across games)
    all_player_stats = {}
    for stats in game_stats.values():
        all_player_stats.update(stats)

    # Settle individual bets
    results = {"settled": 0, "wins": 0, "losses": 0, "pending": 0, "errors": []}
    settled_bet_ids = set()

    for bet in bets:
        team = espn_abbr(bet.get("team", ""))
        bet_id = bet["id"]
        bet_sport = bet.get("sport", "") or detect_sport(team, bet.get("stat", ""))
        game = bet_games.get(bet_id)

        # Check if this bet has a resolved final game
        if game is None:
            # Format the target nicely depending on bet type
            if bet["stat"] == "SPREAD":
                sign = "+" if bet["target"] > 0 else ""
                bet_label = f"{bet['player']} {sign}{bet['target']:g} SPREAD"
            elif bet["stat"] == "ML":
                bet_label = f"{bet['player']} ML"
            else:
                bet_label = f"{bet['player']} {bet['target']:g}+ {bet['stat']}"

            if team in in_progress:
                detail = in_progress[team].get("detail", "in progress")
                if not quiet:
                    print(f"  PENDING: {bet_label} — game still {detail}")
            else:
                if not quiet:
                    print(f"  PENDING: {bet_label} — no game found on today's scoreboard")
            results["pending"] += 1
            continue

        game_sport = game.get("sport", bet_sport or "nba")
        event_id = game["event_id"]

        # Track spread margin for log messages (None for non-spread bets)
        spread_margin = None
        is_push = False

        # Handle moneyline bets — check game winner, not player stats
        if bet["stat"] == "ML":
            # Check if team won via scoreboard (event_id-scoped)
            sport_scoreboard = scoreboards.get(game_sport, {})
            ml_result = check_moneyline(sport_scoreboard, team, event_id=event_id)
            if ml_result is None:
                results["pending"] += 1
                continue
            hit = ml_result
        elif bet["stat"] == "SPREAD":
            # Check spread coverage (signed target: + for dog, - for fav)
            sport_scoreboard = scoreboards.get(game_sport, {})
            covered, spread_margin = check_spread(
                sport_scoreboard, team, bet["target"], event_id=event_id
            )
            if covered is None and spread_margin is None:
                # Game not final yet
                results["pending"] += 1
                continue
            if covered is None:
                # Push — refund wager, no W/L
                is_push = True
                hit = False  # treated as not a win
            else:
                hit = covered
        else:
            # Look up player stats
            player_stats = all_player_stats.get(bet["player"])
            if player_stats is None:
                if not quiet:
                    print(f"  WARNING: {bet['player']} not found in box score"
                          f" for {game['name']}")
                results["errors"].append(f"Player not found: {bet['player']}")
                results["pending"] += 1
                continue

            stat_val = get_stat_value(player_stats, bet["stat"], sport=game_sport)
            if stat_val is None:
                results["errors"].append(
                    f"Stat {bet['stat']} not found for {bet['player']}")
                results["pending"] += 1
                continue

            # Determine W/L
            hit = stat_val >= bet["target"]

        # Only settle straight bets (wager > 0 and no parlay_id) directly.
        # Parlay legs (wager = 0, parlay_id set) get settled with their parlay.
        is_straight = bet.get("wager", 0) > 0 and not bet.get("parlay_id")
        is_parlay_leg = bet.get("parlay_id") is not None

        if is_straight:
            if is_push:
                payout = bet["wager"]  # refund the stake
                result_str = "P"
                results["pending"] += 0  # not really pending, but not counted as W/L
            elif hit:
                payout = calc_payout(bet["wager"], bet.get("odds", 0))
                if payout == 0:
                    payout = bet["wager"]  # fallback: return wager
                    if not quiet:
                        print(f"  WARNING: No odds for bet {bet_id}, payout set to wager amount")
                result_str = "W"
                results["wins"] += 1
            else:
                payout = 0
                result_str = "L"
                results["losses"] += 1

            stat_label = "PRA" if bet["stat"] == "PRA" else bet["stat"]
            icon = "P" if is_push else ("W" if hit else "L")
            if not quiet:
                if bet["stat"] == "ML":
                    result_desc = "WIN" if hit else "LOSS"
                    if hit:
                        print(f"  {icon}: {bet['player']} ML {result_desc}"
                              f" — ${bet['wager']:.2f} bet -> ${payout:.2f} payout")
                    else:
                        print(f"  {icon}: {bet['player']} ML {result_desc}"
                              f" — ${bet['wager']:.2f} lost")
                elif bet["stat"] == "SPREAD":
                    sign = "+" if bet["target"] > 0 else ""
                    spread_str = f"{sign}{bet['target']:g}"
                    margin_str = (f"margin {spread_margin:+d}"
                                  if spread_margin is not None else "")
                    if is_push:
                        print(f"  {icon}: {bet['player']} {spread_str} PUSH"
                              f" ({margin_str}) — ${bet['wager']:.2f} refunded")
                    elif hit:
                        print(f"  {icon}: {bet['player']} {spread_str} COVERED"
                              f" ({margin_str}) — ${bet['wager']:.2f} bet -> ${payout:.2f} payout")
                    else:
                        print(f"  {icon}: {bet['player']} {spread_str} NO COVER"
                              f" ({margin_str}) — ${bet['wager']:.2f} lost")
                else:
                    if hit:
                        print(f"  {icon}: {bet['player']} {stat_val}/{bet['target']} {stat_label}"
                              f" — ${bet['wager']:.2f} bet -> ${payout:.2f} payout")
                    else:
                        print(f"  {icon}: {bet['player']} {stat_val}/{bet['target']} {stat_label}"
                              f" — ${bet['wager']:.2f} lost")

            if not dry_run:
                settle_bet(bet_id, result_str, payout=payout)
            settled_bet_ids.add(bet_id)
            results["settled"] += 1

        elif is_parlay_leg:
            # Track leg results; parlay settled below
            settled_bet_ids.add(bet_id)

    # Settle parlays
    for parlay_id, legs in bet_parlay_legs.items():
        if parlay_id not in parlay_map:
            continue

        parlay = parlay_map[parlay_id]

        # Resolve each leg to its post-placement final game.
        # Use bet_games (already populated above) so the date guard is
        # applied consistently across straight bets and parlay legs.
        leg_games = [bet_games.get(l["id"]) for l in legs]

        # All legs must have a resolved final game
        if any(g is None for g in leg_games):
            if not quiet:
                leg_names = ", ".join(f"{l['player']} {l['stat']}" for l in legs)
                print(f"  PENDING PARLAY: {leg_names} — not all games final")
            results["pending"] += 1
            continue

        # Evaluate each leg
        leg_results = []
        for leg, leg_game in zip(legs, leg_games):
            leg_team = espn_abbr(leg.get("team", ""))
            leg_sport = leg.get("sport", "") or detect_sport(
                leg_team, leg.get("stat", ""))
            game_sport = leg_game.get("sport", leg_sport or "nba")
            leg_event_id = leg_game["event_id"]

            if leg["stat"] == "ML":
                # Moneyline leg — check game winner (event-scoped)
                sport_sb = scoreboards.get(game_sport, {})
                ml_result = check_moneyline(sport_sb, leg_team, event_id=leg_event_id)
                leg_results.append(bool(ml_result))
                continue

            if leg["stat"] == "SPREAD":
                # Spread leg — check coverage (event-scoped)
                sport_sb = scoreboards.get(game_sport, {})
                covered, _margin = check_spread(
                    sport_sb, leg_team, leg["target"], event_id=leg_event_id
                )
                # Treat push as a miss for parlay purposes (DK behavior:
                # parlay drops the leg & recomputes odds, but we don't
                # have that machinery yet — conservative treatment is
                # safer than overpayment).
                leg_results.append(bool(covered))
                continue

            player_stats = all_player_stats.get(leg["player"])
            if player_stats is None:
                leg_results.append(False)
                continue
            stat_val = get_stat_value(
                player_stats, leg["stat"], sport=game_sport)
            if stat_val is None:
                leg_results.append(False)
                continue
            leg_results.append(stat_val >= leg["target"])

        all_hit = all(leg_results)

        if all_hit:
            payout = calc_payout(parlay["wager"], parlay.get("odds", 0))
            if payout == 0:
                payout = parlay["wager"]
                if not quiet:
                    print(f"  WARNING: No odds for parlay {parlay_id},"
                          f" payout set to wager amount")
            result_str = "W"
            results["wins"] += 1
        else:
            payout = 0
            result_str = "L"
            results["losses"] += 1

        leg_summary = " + ".join(
            f"{l['player']} {l['stat']}" for l in legs
        )
        icon = "W" if all_hit else "L"
        if not quiet:
            if all_hit:
                print(f"  {icon}: Parlay ({leg_summary})"
                      f" — ${parlay['wager']:.2f} bet -> ${payout:.2f} payout")
            else:
                # Show which legs missed
                details = []
                for leg, leg_game, hit in zip(legs, leg_games, leg_results):
                    mark = "HIT" if hit else "MISS"
                    if leg["stat"] == "ML":
                        details.append(f"{leg['player']} ML ({mark})")
                    elif leg["stat"] == "SPREAD":
                        sign = "+" if leg["target"] > 0 else ""
                        details.append(
                            f"{leg['player']} {sign}{leg['target']:g} SPREAD ({mark})"
                        )
                    else:
                        lt = espn_abbr(leg.get("team", ""))
                        ls = leg.get("sport", "") or detect_sport(
                            lt, leg.get("stat", ""))
                        gs = leg_game.get("sport", ls or "nba")
                        ps = all_player_stats.get(leg["player"], {})
                        sv = get_stat_value(ps, leg["stat"], sport=gs)
                        details.append(f"{leg['player']} {sv}/{leg['target']} {leg['stat']} ({mark})")
                print(f"  {icon}: Parlay — ${parlay['wager']:.2f} lost")
                for d in details:
                    print(f"       {d}")

        if not dry_run:
            settle_parlay(parlay_id, result_str, payout=payout)
        results["settled"] += 1

    return results


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Auto-settle active bets using ESPN final box scores",
    )
    parser.add_argument(
        "--watch", action="store_true",
        help="Keep checking until all active bets are settled",
    )
    parser.add_argument(
        "--interval", type=int, default=120,
        help="Seconds between checks in watch mode (default: 120)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be settled without making changes",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print output when bets are actually settled",
    )
    args = parser.parse_args()

    if args.dry_run and not args.quiet:
        print("=== DRY RUN — no changes will be made ===\n")

    while True:
        now = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        if not args.quiet:
            print(f"[{now}] Checking active bets...")

        try:
            results = settle_active_bets(
                dry_run=args.dry_run, quiet=args.quiet
            )
        except Exception as e:
            if not args.quiet:
                print(f"  Error: {e}")
            if not args.watch:
                sys.exit(1)
            time.sleep(args.interval)
            continue

        if not args.quiet:
            if results["settled"] > 0:
                print(f"\n  Settled: {results['settled']}"
                      f" ({results['wins']}W-{results['losses']}L)")
            if results["pending"] > 0:
                print(f"  Still pending: {results['pending']}")
            if results["errors"]:
                print(f"  Errors: {', '.join(results['errors'])}")
            print()

        # In quiet mode, only print a summary line when something was settled
        if args.quiet and results["settled"] > 0:
            print(f"[{now}] Settled {results['settled']} bets"
                  f" ({results['wins']}W-{results['losses']}L)")

        if not args.watch:
            break

        if results["pending"] == 0:
            if not args.quiet:
                print("All bets settled. Exiting watch mode.")
            break

        if not args.quiet:
            print(f"Waiting {args.interval}s before next check...\n")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
