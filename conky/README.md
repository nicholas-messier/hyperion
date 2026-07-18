# Conky Desktop Dashboard

Conky desktop widgets showing clock, world time zones, local weather,
system stats, disk usage, and service status at a glance.

Two panels are displayed right-to-left from the screen edge:
- **Clock** (gap_x=20, 320px) — clock, date, world time zones, weather
- **System** (gap_x=360, 320-420px) — CPU, memory, disk, services, conversion pipeline

All personal settings (weather location, disk paths, etc.) are
configured in `config.env` at the repo root and applied during install.
See [`config.env.example`](../config.env.example) for available settings.

---

## Files

| File | Purpose |
|------|---------|
| `conky-clock.conf` | Clock dashboard template (right) — clock, date, world time zones, weather |
| `conky-system.conf` | System stats template (left) — CPU, memory, disk, services, conversion pipeline status |
| `conversion_status.sh` | Helper script used by conky-system to detect active conversion scripts (convert, sync, verify) |
| `update_gpu.sh` | Polls `nvidia-smi` once and writes single-value caches under `~/.cache/gpu_*` so the system panel never blocks on GPU queries |
| `update_weather.sh` | Fetches current conditions from NWS API -> `~/.cache/weather.txt` |
| `update_celtics.sh` | Fetches next game + record from ESPN API -> `~/.cache/celtics_*.txt` |
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
1. Reads `config.env` for your settings (weather station, disk paths, etc.)
2. Installs dependencies (`conky-all`, `jq`, `curl`, `lm-sensors`, `python3-requests`)
3. Checks for JetBrainsMono Nerd Font
4. Generates conky configs from templates, substituting your `config.env` values
5. Deploys configs to `~/.config/conky/`
6. Adds cron jobs (weather every 20 min, sports every 30 min)
7. Runs an initial data fetch so conky has data immediately
8. Creates XDG autostart `.desktop` entries so both panels launch on login
9. Optionally starts conky

---

## Template Placeholders

The `.conf` files in this directory are templates. The `install.sh` script replaces
`__PLACEHOLDER__` markers with values from `config.env`:

| Placeholder | Config Variable | Example |
|-------------|----------------|---------|
| `__WEATHER_LOCATION__` | `WEATHER_LOCATION` | `Your City ST` |
| `__SERVER_HOSTNAME__` | `SERVER_DISPLAY_NAME` (falls back to `$(hostname)`) | `Hyperion` |
| `__CONKY_DATA_DISK__` | `CONKY_DATA_DISK` | `/dev/sdc1` |
| `__CONKY_ARCHIVE_DISK__` | `CONKY_ARCHIVE_DISK` | `/dev/sdb1` |
| `__CONKY_EXTERNAL_DISK__` | `CONKY_EXTERNAL_DISK` | `/media/user/External` |
| `__PLEX_SERVICE__` | `PLEX_SERVICE` | `plexmediaserver` |
| `__MINECRAFT_SERVICE__` | `MINECRAFT_SERVICE` | `minecraft.service` |
| `__ERSATZTV_CONTAINER__` | `ERSATZTV_CONTAINER` | `ersatztv` |
| `__BIN_DIR__` | `BIN_DIR` | `/home/user/bin` |
| `__HOME_DIR__` | `HOME_DIR` (or `$HOME`) | `/home/user` |
| `__TIMEZONE_LINES__` | `CONKY_TIMEZONES` | Generated from TZ config |

---

## Autostart

Both conky panels auto-start on login via XDG `.desktop` entries created by `install.sh`.
To disable autostart, delete the files in `~/.config/autostart/` or set
`X-GNOME-Autostart-enabled=false` inside them.

---

## Manual Start

```bash
conky -c ~/.config/conky/conky-clock.conf -d
conky -c ~/.config/conky/conky-system.conf -d
```

---

## Data Sources

- **Weather:** [NWS API](https://api.weather.gov/) (configurable station via `WEATHER_STATION`)

---

## Dependencies

```bash
sudo apt install conky-all jq curl lm-sensors python3-requests
# JetBrainsMono Nerd Font — https://www.nerdfonts.com/font-downloads
```
