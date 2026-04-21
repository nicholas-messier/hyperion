---
name: sports-betting-upgrade
description: Execute the sports betting advisor upgrade plan (SQLite DB, stats caching, strategy overhaul)
argument-hint: "[phase]"
allowed-tools:
  - read
  - edit
  - grep
  - glob
  - exec
---

# Sports Betting Advisor Upgrade

Execute the upgrade plan for the sports-betting-advisor project. The full plan is documented here:

@../../.devin/plans/sports-betting-upgrade.md

## Instructions

1. Read the full plan above carefully before starting any work.
2. If a specific phase is requested (e.g., `/sports-betting-upgrade phase 1`), execute only that phase. Otherwise, execute all phases in order.
3. Work through each phase sequentially — Phase 1 (SQLite DB) must be complete before Phase 2 (caching) since caching depends on the DB.
4. After each phase, run the relevant verification steps from Phase 4.
5. All new files go in `sports-betting-advisor/` — scripts in `scripts/`, docs in `data/`.
6. Mark the plan status as "In Progress" or "Completed" in the plan file as you go.

## Phase Summary

- **Phase 1:** Create `scripts/db.py` (SQLite), `scripts/migrate_data.py`, update bet_intake/live_tracker/conky dashboard
- **Phase 2:** Add 24hr caching to `nba_stats.py` and `nfl_stats.py` using the DB
- **Phase 3:** Create `data/base_strategy.md`, refactor Celtics postseason doc, update AGENTS.md
- **Phase 4:** Run all verification tests
