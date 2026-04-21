# Sports Betting Advisor

A collection of Python scripts and an AGENTS.md personality file that turns Devin into a data-driven sports betting advisor for NBA and NFL, with a focus on DraftKings odds.

## What's Included

| File | Description |
|------|-------------|
| `AGENTS.md` | Devin personality config — makes Devin act as "Juan Consuelo", a sharp sports betting analyst |
| `scripts/db.py` | **SQLite database module** — single source of truth for bets, bankroll, and stats cache |
| `scripts/migrate_data.py` | **One-time migration** — imports existing markdown/JSON data into the SQLite database |
| `scripts/nba_stats.py` | Fetches NBA player stats (per-game + averages) via the free nba_api. **24hr caching via SQLite.** |
| `scripts/nfl_stats.py` | Fetches NFL player game logs from ESPN's free API. **24hr caching via SQLite.** |
| `scripts/odds_checker.py` | Pulls current DraftKings odds for NBA/NFL via The Odds API |
| `scripts/live_tracker.py` | Real-time bet tracker using ESPN scoreboard API — tracks player props during live games. **Auto-settles bets in DB.** |
| `scripts/bet_intake.py` | HTTP server + OCR pipeline — receives DraftKings screenshots from iPhone and auto-updates active bets. **Writes to DB + JSON.** |
| `data/base_strategy.md` | **Universal betting strategy** — EV framework, confidence tiers, bankroll rules, hedging playbook |
| `data/celtics_postseason_2026.md` | Active betting strategy, bankroll tracker, and bet history for the 2026 Celtics playoff run |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# NBA stats (no API key needed)
python3 scripts/nba_stats.py --player "Stephen Curry" --season 2024

# NFL stats (no API key needed)
python3 scripts/nfl_stats.py --player "Lamar Jackson" --season 2024

# DraftKings odds (free API key required)
export ODDS_API_KEY="your_key"  # Get one at https://the-odds-api.com
python3 scripts/odds_checker.py --sport nba
```

## Database

All bet tracking, bankroll management, and player stats caching use a SQLite database at `~/.config/sports-bets/sports_bets.db`.

```bash
# Initialize the database (creates tables)
python3 scripts/db.py

# Migrate existing data from markdown/JSON into the database
python3 scripts/migrate_data.py

# Preview migration without writing (dry run)
python3 scripts/migrate_data.py --dry-run
```

**Tables:** `bets`, `parlays`, `bankroll_ledger`, `player_stats_cache`

JSON files (`bankroll.json`, `active_bets.json`) are still written for backward compatibility with conky. The `db.sync_json()` function keeps them in sync.

## Data Sources

| Source | Cost | API Key? | Coverage |
|--------|------|----------|----------|
| [nba_api](https://github.com/swar/nba_api) | Free | No | NBA player stats, game logs, season averages (1946-present) |
| [ESPN API](https://www.espn.com) | Free | No | NFL player game logs, stats, team info |
| [The Odds API](https://the-odds-api.com) | Free tier (500 req/mo) | Yes | DraftKings odds — spreads, moneylines, totals |

## Script Details

### NBA Stats (`nba_stats.py`)
- Search any NBA player by name
- Full season game logs with box score stats
- Calculated season averages with shooting splits
- Filter to last N games for recent form analysis

### NFL Stats (`nfl_stats.py`)
- Search any NFL player by name via ESPN
- Full season game logs with position-aware stat columns
- Disambiguates duplicate stats (e.g., passing YDS vs rushing R_YDS)
- Smart averages: rate stats (CMP%, QBR, RTG) show averages only, counting stats show totals + per-game

### Odds Checker (`odds_checker.py`)
- Real-time DraftKings odds for NBA and NFL
- Supports moneyline (h2h), spreads, and totals markets
- Player props support (may require paid API tier)
- Shows API usage to track free tier limits
- Raw JSON output option for programmatic use

### Live Bet Tracker (`live_tracker.py`)
- Tracks active player prop bets against real-time stats during live games
- Uses the free ESPN scoreboard and summary APIs (no API key)
- **Multi-team support:** automatically reads `~/.config/sports-bets/active_bets.json` and finds games for all teams with active bets
- Progress bars show how close each bet is to hitting
- Parlay tracking across multiple legs
- Auto-refreshes every 30 seconds (configurable)
- **Daemon mode (`--daemon`):** runs in the background, writes state to `~/.cache/sports-bets/live_tracker.log`, manages a PID file for lifecycle control
- **Auto-triggered** by the conky sports dashboard and the `game_monitor.py` cron job whenever a tracked game goes live

## How It Works with Devin

1. Place the `AGENTS.md` file in your repo root
2. When you chat with Devin, it will adopt "The Edge" personality
3. Ask for picks or analysis — Devin will run the scripts to pull real data
4. Get data-backed recommendations with confidence ratings

Example prompts:
- "What do you think about Jokic over 25.5 points tonight?"
- "Give me your best NFL picks for this week's games"
- "Check the DraftKings spread for tonight's Lakers game"
- "How has Lamar Jackson been playing the last 5 games?"

---

## Bet Intake (iPhone → Server → Conky)

The bet intake server lets you share DraftKings bet slip screenshots from your iPhone
and have them automatically parsed and displayed in the conky live tracker.

### Pipeline

```
DraftKings app → Share → iOS Shortcut → HTTP POST → bet_intake.py → OCR → active_bets.json → conky
```

### Server Setup

The intake server runs as a systemd user service and starts on boot:

```bash
# Already set up — check status
systemctl --user status bet-intake

# Manual start/stop
systemctl --user start bet-intake
systemctl --user stop bet-intake

# View logs
journalctl --user -u bet-intake -f
```

Config in `config.env`:
```
INTAKE_PORT="8420"
INTAKE_TOKEN="your-secret-token"
```

### iOS Shortcut Setup

Create an iOS Shortcut named **"Send to Server"** with these steps:

1. **Receive** `Images` input from **Share Sheet**
2. **Get Contents of URL**:
   - URL: `http://<INTAKE_PUBLIC_IP>:<INTAKE_PORT>/upload`
     (use your public IP from `config.env`, e.g., `http://73.x.x.x:8420/upload`)
   - Method: **POST**
   - Headers:
     - `Authorization` → `Bearer <INTAKE_TOKEN>`
   - Request Body: **File**
   - File: **Shortcut Input**
3. **Get Dictionary Value** — key: `bets_found`
4. **Show Notification**: `Found [Dictionary Value] bets`

Requires router port forwarding: external port 8420 → internal 192.168.0.16:8420 (TCP).

Then from DraftKings: **Share bet slip → tap "Send to Server"** in the share sheet.

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload bet slip image (OCR + parse → updates active bets) |
| `POST` | `/bets` | Submit bets as JSON directly |
| `GET` | `/bets` | View current active bets |
| `DELETE` | `/bets` | Clear all active bets |
| `GET` | `/health` | Health check |

### CLI Usage

```bash
# Process a local screenshot
python3 scripts/bet_intake.py --file /path/to/screenshot.png

# Clear all bets
python3 scripts/bet_intake.py --clear

# Start server manually (for testing)
python3 scripts/bet_intake.py --port 8420 --token mysecret
```

### Dependencies

```bash
sudo apt install tesseract-ocr
pip install pillow  # or: already included in system python
```
