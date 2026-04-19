# Conky Desktop Dashboard

Conky desktop widgets showing clock, world time zones, local weather,
sports/betting dashboard, system stats, disk usage, and service status at a glance.

Three panels are displayed right-to-left from the screen edge:
- **Clock** (gap_x=20, 320px) — clock, date, world time zones, weather
- **Sports** (gap_x=360, 320px) — NBA Playoffs, active bets, bankroll status
- **System** (gap_x=700, 320-420px) — CPU, memory, disk, services, conversion pipeline

All personal settings (weather location, sports team, disk paths, etc.) are
configured in `config.env` at the repo root and applied during install.
See [`config.env.example`](../config.env.example) for available settings.

---

## Files

| File | Purpose |
|------|---------|
| `conky-clock.conf` | Clock dashboard template (right) — clock, date, world time zones, weather |
| `conky-sports.conf` | Sports dashboard template (middle) — NBA Playoffs, active bets, bankroll status |
| `conky-system.conf` | System stats template (left) — CPU, memory, disk, services, conversion pipeline status |
| `conversion_status.sh` | Helper script used by conky-system to detect active conversion scripts (convert, sync, verify) |
| `update_weather.sh` | Fetches current conditions from NWS API -> `~/.cache/weather.txt` |
| `update_celtics.sh` | Fetches next game + record from ESPN API -> `~/.cache/celtics_*.txt` |
| `update_sports.py` | Smart sports display — shows live bet tracking during games, schedule otherwise |
| `update_sports_dashboard.py` | Full sports panel — playoffs, active bets with live progress, bankroll status |
| `install.sh` | One-command setup: installs deps, generates configs from templates, sets up cron, starts conky |

---

## Quick Setup

```bash
# Make sure config.env exists first
cp ../config.env.example ../config.env
$EDITOR ../config.env

# Run the installer
cd conky/
./install.sh
```

The install script:
1. Reads `config.env` for your settings (weather station, sports team, disk paths, etc.)
2. Installs dependencies (`conky-all`, `jq`, `curl`, `lm-sensors`, `python3-requests`)
3. Checks for JetBrainsMono Nerd Font
4. Generates conky configs from templates, substituting your `config.env` values
5. Deploys configs to `~/.config/conky/`
6. Adds cron jobs (weather every 20 min, sports every 30 min)
7. Runs an initial data fetch so conky has data immediately
8. Creates XDG autostart `.desktop` entries so all three panels launch on login
9. Optionally starts conky

---

## Template Placeholders

The `.conf` files in this directory are templates. The `install.sh` script replaces
`__PLACEHOLDER__` markers with values from `config.env`:

| Placeholder | Config Variable | Example |
|-------------|----------------|---------|
| `__WEATHER_LOCATION__` | `WEATHER_LOCATION` | `Your City ST` |
| `__SPORTS_TEAM_NAME__` | `SPORTS_TEAM_NAME` | `Celtics` |
| `__SERVER_HOSTNAME__` | (auto-detected) | `myserver` |
| `__CONKY_DATA_DISK__` | `CONKY_DATA_DISK` | `/dev/sdc1` |
| `__CONKY_ARCHIVE_DISK__` | `CONKY_ARCHIVE_DISK` | `/dev/sdb1` |
| `__CONKY_EXTERNAL_DISK__` | `CONKY_EXTERNAL_DISK` | `/media/user/External` |
| `__PLEX_SERVICE__` | `PLEX_SERVICE` | `plexmediaserver` |
| `__MINECRAFT_SERVICE__` | `MINECRAFT_SERVICE` | `minecraft.service` |
| `__ERSATZTV_CONTAINER__` | `ERSATZTV_CONTAINER` | `ersatztv` |
| `__BIN_DIR__` | `BIN_DIR` | `/home/user/bin` |
| `__TIMEZONE_LINES__` | `CONKY_TIMEZONES` | Generated from TZ config |

---

## Autostart

All three conky panels auto-start on login via XDG `.desktop` entries created by `install.sh`.
To disable autostart, delete the files in `~/.config/autostart/` or set
`X-GNOME-Autostart-enabled=false` inside them.

---

## Manual Start

```bash
conky -c ~/.config/conky/conky-clock.conf -d
conky -c ~/.config/conky/conky-sports.conf -d
conky -c ~/.config/conky/conky-system.conf -d
```

---

## Data Sources

- **Weather:** [NWS API](https://api.weather.gov/) (configurable station via `WEATHER_STATION`)
- **Sports:** [ESPN API](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/) (configurable team via `SPORTS_TEAM`)

---

## Live Bet Tracking

The sports panel automatically shows bet progress when games are live:

**Static mode (default):** Lists all active bets with player, stat target, and wager amount.

**Live tracking mode:** When an NBA game is in progress (or just finished) and you have active
bets on players in that game, the display switches to show real-time bet progress:

```
Celtics: (64-18)
LIVE  BOS 85-ATL 72 Q3 4:32
  ✓ Brown PTS 30/25        ← hit
  ◆ Tatum REB 8/10         ← in progress
  Parlay A: 1/2 legs
```

This works for **any NBA team**, not just the Celtics. Bets on Lakers, Warriors, etc. will
all trigger live tracking when those games are in progress.

### Managing Active Bets

Active bets are defined in `~/.config/sports-bets/active_bets.json`:

```json
{
    "bets": [
        {"player": "Jaylen Brown", "team": "BOS", "stat": "PTS", "target": 25, "wager": 5.00},
        {"player": "Jayson Tatum", "team": "BOS", "stat": "REB", "target": 10, "wager": 3.00},
        {"player": "LeBron James", "team": "LAL", "stat": "PTS", "target": 28, "wager": 4.00}
    ],
    "parlays": [
        {"name": "A", "legs": ["Jaylen Brown:PTS:25", "Jayson Tatum:REB:10"], "wager": 2.00}
    ]
}
```

**Bet fields:**
- `player` — Full ESPN display name (e.g., "Jaylen Brown")
- `team` — ESPN team abbreviation (e.g., "BOS", "LAL", "GSW")
- `stat` — Stat to track: `PTS`, `REB`, `AST`, `STL`, `BLK`, `3PT`, or `PRA` (pts+reb+ast)
- `target` — The over threshold (e.g., 25 means 25+)
- `wager` — Dollar amount wagered

**To clear bets** (return to schedule-only display), empty the bets array:
```json
{"bets": [], "parlays": []}
```

The display refreshes every 60 seconds. When no bets are active or no matching games are
live, it automatically falls back to showing the next Celtics game schedule.

---

## Bankroll Tracking

The sports panel displays bankroll status from `~/.config/sports-bets/bankroll.json`:

```json
{
    "starting_bankroll": 20.00,
    "total_deposited": 40.00,
    "current_balance": 36.33,
    "in_play": 16.00,
    "wins": 3,
    "losses": 0
}
```

**Fields:**
- `starting_bankroll` — Initial deposit amount
- `total_deposited` — Total money deposited across all deposits
- `current_balance` — Current unwagered balance on DraftKings
- `in_play` — Total amount currently wagered on active bets
- `wins` / `losses` — Win-loss record

**Display:** The panel shows balance (green if above starting, red if below), net P/L
(calculated as `current_balance + in_play - total_deposited`), and win-loss record.

This file is updated by the betting advisor (Devin "Juan Consuelo" personality) alongside
the markdown strategy doc during betting sessions.

---

## Dependencies

```bash
sudo apt install conky-all jq curl lm-sensors python3-requests
# JetBrainsMono Nerd Font — https://www.nerdfonts.com/font-downloads
```
