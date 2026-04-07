# Conky Desktop Dashboard

Conky desktop widgets for Hyperion showing clock, world time zones, local weather (Laconia NH),
Boston Celtics schedule, system stats, disk usage, and service status at a glance.

---

## Files

| File | Purpose |
|------|---------|
| `conky-clock.conf` | Main dashboard widget (top-right) — clock, date, world time zones, weather, Celtics |
| `conky-system.conf` | System stats widget — CPU, memory, disk, services, conversion pipeline status |
| `conversion_status.sh` | Helper script used by conky-system to detect active conversion scripts (convert, sync, verify) |
| `update_weather.sh` | Fetches current conditions from NWS API (KLCI station) -> `~/.cache/wttr_laconia.txt` |
| `update_celtics.sh` | Fetches next Celtics game + record from ESPN API -> `~/.cache/celtics_*.txt` |
| `install.sh` | One-command setup: installs deps, deploys configs, sets up cron, starts conky |

---

## Quick Setup

```bash
cd conky/
./install.sh
```

The install script:
1. Installs dependencies (`conky-all`, `jq`, `curl`, `lm-sensors`)
2. Checks for JetBrainsMono Nerd Font
3. Copies conky configs to `~/.config/conky/`
4. Adds cron jobs (weather every 20 min, Celtics every 30 min)
5. Runs an initial data fetch so conky has data immediately
6. Optionally starts conky

---

## Manual Start

```bash
conky -c ~/.config/conky/conky-clock.conf -d
```

---

## Data Sources

- **Weather:** [NWS API](https://api.weather.gov/) (station KLCI — Laconia Municipal Airport)
- **Celtics:** [ESPN API](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/)

---

## Dependencies

```bash
sudo apt install conky-all jq curl lm-sensors
# JetBrainsMono Nerd Font — https://www.nerdfonts.com/font-downloads
```
