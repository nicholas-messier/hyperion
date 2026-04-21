# Sports Betting Advisor — Upgrade Plan

**Created:** April 21, 2026
**Status:** Completed — all 4 phases implemented and verified (April 21, 2026)
**Scope:** Database, caching, strategy overhaul for `sports-betting-advisor/`

---

## Overview

Introduce a SQLite database as the single source of truth for all bet tracking, bankroll management, and player stats caching. Create a base strategy document with universal value betting, hedging, and high-value bet identification guidelines. Refactor the Celtics postseason doc to inherit from the base. Modify the stats scripts to cache player data for 24 hours to reduce redundant API calls.

### User Preferences (from planning session)

- **Data store:** SQLite database
- **Strategy structure:** Base doc + sport/event-specific docs that inherit from it
- **Value bet finder:** Strategy guidelines in the docs (not a separate automated script)
- **Cache TTL:** 24 hours

---

## Phase 1: SQLite Database Foundation

### New file: `scripts/db.py` — Database module

The central data layer. Creates and manages `~/.config/sports-bets/sports_bets.db`.

#### Schema

**`bets` table:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| placed_at | TEXT | ISO datetime |
| player | TEXT | Player name |
| team | TEXT | Team abbreviation |
| sport | TEXT | "nba" or "nfl" |
| stat | TEXT | PTS, REB, AST, etc. |
| target | REAL | The over/under line |
| odds | INTEGER | American odds (e.g., -132) |
| wager | REAL | Dollar amount |
| confidence | TEXT | Lock/Strong Lean/Lean |
| result | TEXT | NULL (pending), "W", "L" |
| payout | REAL | Actual payout (0 if loss) |
| settled_at | TEXT | When the bet was settled |
| parlay_id | INTEGER FK | NULL for straight bets |
| notes | TEXT | Optional context |

**`parlays` table:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| placed_at | TEXT | ISO datetime |
| odds | INTEGER | Combined parlay odds |
| wager | REAL | Parlay wager |
| result | TEXT | NULL, "W", "L" |
| payout | REAL | Actual payout |
| settled_at | TEXT | When settled |

**`bankroll_ledger` table:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| timestamp | TEXT | ISO datetime |
| action | TEXT | deposit, withdrawal, bet_placed, bet_settled |
| amount | REAL | Signed dollar amount |
| balance | REAL | Running balance after this action |
| reference_id | INTEGER | Bet or parlay ID (nullable) |
| notes | TEXT | Optional description |

**`player_stats_cache` table:**

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| player_name | TEXT | Normalized name |
| sport | TEXT | "nba" or "nfl" |
| season | TEXT | Season string (e.g., "2025-26") |
| fetched_at | TEXT | ISO datetime of last fetch |
| game_log_json | TEXT | Full game log as JSON |
| averages_json | TEXT | Calculated averages as JSON |
| games_played | INTEGER | For quick reference |

#### Key functions in `db.py`

- `init_db()` — create tables if not exist, enable WAL mode
- `record_bet()` / `record_parlay()` — insert new bets
- `settle_bet()` — update result, payout, and bankroll ledger
- `get_active_bets()` — bets with NULL result
- `get_bet_history()` — full history with filters (date, player, sport)
- `get_bankroll()` — current balance, total deposited, W-L record, net P/L
- `update_bankroll()` — add ledger entry
- `cache_player_stats()` / `get_cached_stats()` — stats caching with 24hr TTL
- `get_frequent_players()` — players bet on most often (for priority caching)
- `sync_json()` — write current state to `bankroll.json` and `active_bets.json` for backward compatibility with conky

### New file: `scripts/migrate_data.py` — One-time migration

Parses the existing data into the new database:

- Reads bet history from `data/celtics_postseason_2026.md` (the markdown table)
- Reads bankroll ledger entries from the same file
- Imports current active bets from `~/.config/sports-bets/active_bets.json`
- Populates all tables with historical data
- Should be reviewed manually after running — markdown parsing can be fragile

### Modified: `scripts/bet_intake.py`

- After parsing a bet slip, also write to the SQLite DB via `db.record_bet()`
- Call `db.sync_json()` to keep JSON files in sync for conky
- Keep existing JSON write path as a fallback if DB is unavailable

### Modified: `scripts/live_tracker.py`

- Read active bets from DB via `db.get_active_bets()` (fall back to JSON)
- When a bet resolves (game final + stat confirmed), call `db.settle_bet()`
- Auto-update bankroll ledger on settlement

### Modified: `conky/update_sports_dashboard.py`

- Read bankroll from DB via `db.get_bankroll()` (fall back to JSON file)
- No structural changes — just swap the data source

---

## Phase 2: Player Stats Caching

### Modified: `scripts/nba_stats.py`

- Import `db.py` and check cache before hitting the nba_api
- If cached data exists and is < 24 hours old, display from cache
- If stale or missing, fetch from API, display, and write to cache
- Add `--refresh` flag to force a fresh API call regardless of cache
- Add `--cache-status` flag to show what's cached for a player

### Modified: `scripts/nfl_stats.py`

- Same caching pattern as nba_stats.py
- Check DB cache first, fetch from ESPN API only if stale
- Add `--refresh` flag

### Auto-cache frequently bet players

- `db.get_frequent_players()` returns players ranked by bet count
- The advisor (via AGENTS.md instructions) can be told to pre-cache these players at session start
- Optionally add a `scripts/refresh_cache.py` utility that refreshes stats for all frequently-bet players in one batch (could be run as a cron job)

---

## Phase 3: Base Strategy Document

### New file: `data/base_strategy.md` — Universal betting strategy

Covers everything that applies across all sports and seasons:

1. **Philosophy** — The Grinder approach, discipline, data-driven decisions
2. **Confidence Tier System** — Lock/Strong Lean/Lean/Fade definitions and rules
3. **Bankroll Management** (percentage-based, not dollar amounts):
   - Bet sizing tiers by confidence level (percentage of bankroll)
   - Daily exposure limit (30%)
   - Parlay rules (max 2-leg, both legs Strong Lean+)
   - Never chase losses
   - Milestone withdrawal rules
4. **Odds Floor Rules** — No straight bets past -200, parlay super-juiced props, the sweet spot
5. **Value Betting Framework** (new):
   - **Expected Value (EV) calculation:** `EV = (hit_rate x net_payout) - ((1 - hit_rate) x wager)`. Only bet when EV > 0.
   - **Implied probability vs. actual probability:** Convert American odds to implied probability, compare against actual hit rate from stats.
   - **"The Value Zone"** — where hit rate exceeds implied probability by 10%+. These are the highest priority bets.
   - **Line shopping rules:** Compare DraftKings lines against the data. If DK's line is higher than recent performance, that's value. If it's lower, the books are pricing in what we know.
   - **Contrarian plays:** When public money pushes a line in one direction, the other side may have value. Use stats to validate.
6. **High-Value Bet Identification** (new):
   - **Systematic scanning process:** For each game day, pull stats + odds for all relevant players. Calculate EV for each prop. Rank by EV.
   - **Priority order:** Value Zone bets > Lock with good odds > Strong Lean with great odds > skip everything else.
   - **"Inefficiency targets":** Less popular props (rebounds, assists, blocks) are often less efficiently priced than points. Exploit this.
   - **Alternate lines:** Sometimes the alternate line (e.g., Over 12.5 REB instead of Over 10.5 REB) offers better value due to odds misalignment.
7. **Hedging Playbook** (expanded from current doc):
   - Correlated props
   - Opposite side hedge (for larger bankrolls)
   - Series-level hedging
   - Prop diversification across games
   - **Live betting hedges** (new) — when to use DK's cash-out vs. manual hedge
   - **When NOT to hedge** — don't hedge low-confidence bets, don't hedge if the cost exceeds 30% of potential payout
8. **Sport-Specific Notes:**
   - NBA: Focus on player props (PTS, REB, AST), check last 10 games, watch for blowout risk
   - NFL: Watch for weather, injury reports, check last 5 games, position-specific prop rules

### Modified: `data/celtics_postseason_2026.md`

Refactor to remove content that's now in the base doc:

- Remove duplicated bankroll management rules (reference base doc)
- Remove duplicated hedging strategies (reference base doc)
- Remove duplicated confidence tier definitions (reference base doc)
- Keep: Bankroll tracker, active bets, bet history, player profiles, round-by-round game plan, session notes
- Add: Reference to `base_strategy.md` at the top

### Modified: `AGENTS.md`

Update the advisor's instructions:

- **At session start:** Read `data/base_strategy.md` first, then the active event doc (e.g., `data/celtics_postseason_2026.md`)
- **When evaluating a bet:** Follow the EV framework from base strategy before presenting picks
- **Add to pick format:** Include EV calculation and whether the bet is in the "Value Zone"
- **Add workflow step:** "Step 2.5: Calculate Value" — after pulling stats and odds, calculate EV before deciding whether to recommend
- **New instruction:** "Prioritize high-value bets. Don't just look for likely winners — look for mispriced lines where the data gives us an edge the books haven't fully priced in."

---

## Phase 4: Verification

### Tests to run

- `python3 scripts/db.py` — verify tables create properly (add a `__main__` block that runs init_db and prints table info)
- `python3 scripts/migrate_data.py` — verify historical data imports correctly, spot-check bet history counts and bankroll balance
- `python3 scripts/nba_stats.py --player "Jaylen Brown" --season 2025` — run twice, second should be instant (cached)
- `python3 scripts/nba_stats.py --player "Jaylen Brown" --season 2025 --refresh` — verify force refresh
- Check that `~/.config/sports-bets/bankroll.json` and `active_bets.json` are still written correctly after DB operations
- Verify `conky/update_sports_dashboard.py` still renders correctly (take a screenshot with `DISPLAY=:0 gnome-screenshot -f /tmp/screenshot.png`)

---

## Files Summary

| File | Status | Description |
|------|--------|-------------|
| `scripts/db.py` | **NEW** | SQLite database module |
| `scripts/migrate_data.py` | **NEW** | One-time data migration from markdown/JSON |
| `data/base_strategy.md` | **NEW** | Universal betting strategy doc |
| `scripts/nba_stats.py` | MODIFY | Add 24hr caching layer, --refresh flag |
| `scripts/nfl_stats.py` | MODIFY | Add 24hr caching layer, --refresh flag |
| `scripts/bet_intake.py` | MODIFY | Write to DB + JSON |
| `scripts/live_tracker.py` | MODIFY | Read from DB, settle bets to DB |
| `conky/update_sports_dashboard.py` | MODIFY | Read bankroll from DB |
| `data/celtics_postseason_2026.md` | MODIFY | Refactor, reference base doc |
| `AGENTS.md` | MODIFY | Update advisor instructions for EV framework |
| `README.md` | MODIFY | Document new database and strategy docs |
| `requirements.txt` | NO CHANGE | sqlite3 is stdlib, no new deps |

---

## Risks & Considerations

- **Migration accuracy:** Parsing bet history from markdown is fragile. Review manually after running.
- **Backward compatibility:** Conky reads JSON files. `sync_json()` keeps this working, but any script that modifies bets must call it.
- **DB concurrency:** SQLite WAL mode handles concurrent reads (conky + live tracker). Single writer at a time is fine for this use case.
- **Cache invalidation edge case:** If a player is traded mid-season, cached stats may be misleading. The 24hr TTL limits this risk.
- **No new dependencies:** sqlite3 is Python stdlib. No changes to requirements.txt.

---

## How to Execute This Plan

In a future Devin session, say something like:

> "Execute the sports betting upgrade plan in `.devin/plans/sports-betting-upgrade.md`"

Devin will read this file and implement each phase in order.
