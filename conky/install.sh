#!/bin/bash
# install.sh — Deploy conky desktop widget and its helper scripts
#
# Run this after cloning the repo on a new machine:
#   cd ~/bin/conky && ./install.sh
#
# What it does:
#   1. Installs dependencies (conky, jq, curl, lm-sensors)
#   2. Copies conky configs to ~/.config/conky/
#   3. Adds cron jobs for weather + Celtics data updates
#   4. Runs the data scripts once so conky has data on first launch
#   5. Optionally starts conky

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors (disabled when piped)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BLUE='' NC=''
fi

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------- 1. Dependencies ----------
info "Checking dependencies..."

DEPS=(conky-all jq curl lm-sensors)
MISSING=()

for pkg in "${DEPS[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Missing packages: ${MISSING[*]}"
    read -rp "Install them now? (requires sudo) [Y/n] " ans
    ans=${ans:-Y}
    if [[ "$ans" =~ ^[Yy] ]]; then
        sudo apt update && sudo apt install -y "${MISSING[@]}"
        ok "Dependencies installed"
    else
        warn "Skipping dependency install — conky may not work correctly"
    fi
else
    ok "All dependencies already installed"
fi

# Check for JetBrainsMono Nerd Font (used by conky-clock.conf)
if ! fc-list | grep -qi "JetBrainsMono.*Nerd"; then
    warn "JetBrainsMono Nerd Font not found"
    echo "     conky-clock.conf uses this font — install it from:"
    echo "     https://www.nerdfonts.com/font-downloads"
    echo "     or: sudo apt install fonts-jetbrains-mono  (base font, no Nerd icons)"
else
    ok "JetBrainsMono Nerd Font found"
fi

# ---------- 2. Deploy conky configs ----------
info "Deploying conky configs to ~/.config/conky/..."

CONKY_DIR="$HOME/.config/conky"
mkdir -p "$CONKY_DIR"

for conf in conky-clock.conf conky-weather.conf; do
    if [ -f "$CONKY_DIR/$conf" ]; then
        if ! diff -q "$SCRIPT_DIR/$conf" "$CONKY_DIR/$conf" &>/dev/null; then
            warn "$conf already exists and differs — backing up to ${conf}.bak"
            cp "$CONKY_DIR/$conf" "$CONKY_DIR/${conf}.bak"
        fi
    fi
    cp "$SCRIPT_DIR/$conf" "$CONKY_DIR/$conf"
    ok "Installed $conf"
done

# ---------- 3. Make helper scripts executable ----------
info "Setting permissions on helper scripts..."
chmod +x "$SCRIPT_DIR/update_weather.sh"
chmod +x "$SCRIPT_DIR/update_celtics.sh"
ok "Scripts are executable"

# ---------- 4. Cron jobs ----------
info "Setting up cron jobs..."

WEATHER_CRON="*/20 * * * * $SCRIPT_DIR/update_weather.sh"
CELTICS_CRON="*/30 * * * * $SCRIPT_DIR/update_celtics.sh"

CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)

add_cron_entry() {
    local entry="$1"
    local script_name="$2"

    # Remove any existing entry for this script (old or new path)
    CURRENT_CRONTAB=$(echo "$CURRENT_CRONTAB" | grep -v "$script_name" || true)

    # Add the new entry
    CURRENT_CRONTAB="${CURRENT_CRONTAB}
${entry}"
}

add_cron_entry "$WEATHER_CRON" "update_weather.sh"
add_cron_entry "$CELTICS_CRON" "update_celtics.sh"

# Clean up blank lines and install
echo "$CURRENT_CRONTAB" | sed '/^$/d' | crontab -
ok "Cron jobs installed"
echo "     Weather updates:  every 20 minutes"
echo "     Celtics updates:  every 30 minutes"

# ---------- 5. Initial data fetch ----------
info "Running initial data fetch (weather + Celtics)..."
mkdir -p "$HOME/.cache"

if "$SCRIPT_DIR/update_weather.sh" 2>/dev/null; then
    ok "Weather data fetched"
else
    warn "Weather fetch failed — will retry on next cron run"
fi

if "$SCRIPT_DIR/update_celtics.sh" 2>/dev/null; then
    ok "Celtics data fetched"
else
    warn "Celtics fetch failed — will retry on next cron run (may fail in offseason)"
fi

# ---------- 6. Optionally start conky ----------
echo ""
read -rp "Start conky now? [Y/n] " ans
ans=${ans:-Y}
if [[ "$ans" =~ ^[Yy] ]]; then
    # Kill any existing conky instances
    killall conky 2>/dev/null || true
    sleep 1
    conky -c "$CONKY_DIR/conky-clock.conf" -d
    ok "Conky started (conky-clock.conf)"
    echo ""
    echo "To auto-start conky on login, add this to your startup applications:"
    echo "  conky -c $CONKY_DIR/conky-clock.conf -d"
else
    info "Skipped — start manually with:"
    echo "  conky -c $CONKY_DIR/conky-clock.conf -d"
fi

echo ""
ok "Conky setup complete!"
echo ""
echo "Files:"
echo "  Configs:  $CONKY_DIR/conky-clock.conf"
echo "            $CONKY_DIR/conky-weather.conf"
echo "  Scripts:  $SCRIPT_DIR/update_weather.sh"
echo "            $SCRIPT_DIR/update_celtics.sh"
echo "  Cache:    ~/.cache/wttr_laconia.txt"
echo "            ~/.cache/celtics_record.txt"
echo "            ~/.cache/celtics_next.txt"
