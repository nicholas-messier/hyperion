#!/bin/bash
# install.sh — Deploy conky desktop widget and its helper scripts
#
# Run this after cloning the repo on a new machine:
#   cd ~/bin/conky && ./install.sh
#
# What it does:
#   1. Sources config.env for server-specific values
#   2. Installs dependencies (conky, jq, curl, lm-sensors)
#   3. Generates conky configs from templates using config.env values
#   4. Deploys configs to ~/.config/conky/
#   5. Adds cron jobs for weather + sports data updates
#   6. Runs the data scripts once so conky has data on first launch
#   7. Sets up XDG autostart entries so conky launches on login
#   8. Optionally starts conky

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------- 0. Source config.env ----------
if [[ ! -f "$REPO_ROOT/config.env" ]]; then
    echo "ERROR: config.env not found at $REPO_ROOT/config.env"
    echo ""
    echo "Copy the example and fill in your values:"
    echo "  cp $REPO_ROOT/config.env.example $REPO_ROOT/config.env"
    echo "  \$EDITOR $REPO_ROOT/config.env"
    exit 1
fi

# shellcheck source=../config.env
source "$REPO_ROOT/config.env"

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

DEPS=(conky-all jq curl lm-sensors python3-requests)
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

# ---------- 2. Generate and deploy conky configs ----------
info "Generating conky configs from templates..."

CONKY_DIR="$HOME/.config/conky"
mkdir -p "$CONKY_DIR"

# Build timezone lines for conky-clock.conf from CONKY_TIMEZONES
# Format: "TZ_ID:Label,TZ_ID:Label,..."
generate_timezone_lines() {
    local tz_config="${CONKY_TIMEZONES:-America/New_York:Eastern}"
    local lines=""
    IFS=',' read -ra TZ_ENTRIES <<< "$tz_config"
    for entry in "${TZ_ENTRIES[@]}"; do
        local tz_id="${entry%%:*}"
        local label="${entry#*:}"
        # Pad label to align the time output (14 chars)
        local padded
        padded=$(printf '%-14s' "$label:")
        lines+="\${color #add8e6}${padded}\${color}  \${tztime ${tz_id} %I:%M %p}"$'\n'
    done
    # Remove trailing newline
    echo -n "${lines%$'\n'}"
}

TIMEZONE_LINES=$(generate_timezone_lines)

# Template substitution function
apply_template() {
    local src="$1"
    local dst="$2"

    # Backup existing config if it differs
    if [ -f "$dst" ]; then
        # Compare against what we'd generate, not the template
        local tmp
        tmp=$(mktemp)
        cp "$src" "$tmp"
        # Apply substitutions to temp file
        sed -i \
            -e "s|__WEATHER_LOCATION__|${WEATHER_LOCATION:-Your City}|g" \
            -e "s|__SPORTS_TEAM_NAME__|${SPORTS_TEAM_NAME:-Team}|g" \
            -e "s|__SERVER_HOSTNAME__|${SERVER_DISPLAY_NAME:-$(hostname)}|g" \
            -e "s|__CONKY_DATA_DISK__|${CONKY_DATA_DISK:-/}|g" \
            -e "s|__CONKY_ARCHIVE_DISK__|${CONKY_ARCHIVE_DISK:-/}|g" \
            -e "s|__CONKY_EXTERNAL_DISK__|${CONKY_EXTERNAL_DISK:-/mnt/external}|g" \
            -e "s|__PLEX_SERVICE__|${PLEX_SERVICE:-plexmediaserver}|g" \
            -e "s|__MINECRAFT_SERVICE__|${MINECRAFT_SERVICE:-minecraft.service}|g" \
            -e "s|__ERSATZTV_CONTAINER__|${ERSATZTV_CONTAINER:-ersatztv}|g" \
            -e "s|__BIN_DIR__|${BIN_DIR:-$REPO_ROOT}|g" \
            -e "s|__HOME_DIR__|${HOME_DIR:-$HOME}|g" \
            "$tmp"

        if ! diff -q "$tmp" "$dst" &>/dev/null; then
            warn "$(basename "$dst") already exists and differs — backing up to $(basename "$dst").bak"
            cp "$dst" "${dst}.bak"
        fi
        rm -f "$tmp"
    fi

    cp "$src" "$dst"

    # Apply all template substitutions
    sed -i \
        -e "s|__WEATHER_LOCATION__|${WEATHER_LOCATION:-Your City}|g" \
        -e "s|__SPORTS_TEAM_NAME__|${SPORTS_TEAM_NAME:-Team}|g" \
        -e "s|__SERVER_HOSTNAME__|${SERVER_DISPLAY_NAME:-$(hostname)}|g" \
        -e "s|__CONKY_DATA_DISK__|${CONKY_DATA_DISK:-/}|g" \
        -e "s|__CONKY_ARCHIVE_DISK__|${CONKY_ARCHIVE_DISK:-/}|g" \
        -e "s|__CONKY_EXTERNAL_DISK__|${CONKY_EXTERNAL_DISK:-/mnt/external}|g" \
        -e "s|__PLEX_SERVICE__|${PLEX_SERVICE:-plexmediaserver}|g" \
        -e "s|__MINECRAFT_SERVICE__|${MINECRAFT_SERVICE:-minecraft.service}|g" \
        -e "s|__ERSATZTV_CONTAINER__|${ERSATZTV_CONTAINER:-ersatztv}|g" \
        -e "s|__BIN_DIR__|${BIN_DIR:-$REPO_ROOT}|g" \
        -e "s|__HOME_DIR__|${HOME_DIR:-$HOME}|g" \
        "$dst"

    # Replace timezone placeholder with generated lines (multi-line)
    if grep -q "__TIMEZONE_LINES__" "$dst"; then
        local escaped_tz
        escaped_tz=$(echo "$TIMEZONE_LINES" | sed 's/[&/\]/\\&/g; s/$/\\/' | sed '$ s/\\$//')
        sed -i "s|__TIMEZONE_LINES__|${escaped_tz}|" "$dst"
    fi
}

# Deploy clock and system configs from templates
for conf in conky-clock.conf conky-system.conf conky-sports.conf; do
    if [ -f "$SCRIPT_DIR/$conf" ]; then
        apply_template "$SCRIPT_DIR/$conf" "$CONKY_DIR/$conf"
        ok "Generated and installed $conf"
    fi
done

# Copy weather config as-is (no template vars)
if [ -f "$SCRIPT_DIR/conky-weather.conf" ]; then
    if [ -f "$CONKY_DIR/conky-weather.conf" ]; then
        if ! diff -q "$SCRIPT_DIR/conky-weather.conf" "$CONKY_DIR/conky-weather.conf" &>/dev/null; then
            warn "conky-weather.conf already exists and differs — backing up"
            cp "$CONKY_DIR/conky-weather.conf" "$CONKY_DIR/conky-weather.conf.bak"
        fi
    fi
    cp "$SCRIPT_DIR/conky-weather.conf" "$CONKY_DIR/conky-weather.conf"
    ok "Installed conky-weather.conf"
fi

# ---------- 3. Make helper scripts executable ----------
info "Setting permissions on helper scripts..."
chmod +x "$SCRIPT_DIR/update_weather.sh"
chmod +x "$SCRIPT_DIR/update_celtics.sh"
chmod +x "$SCRIPT_DIR/update_sports.py"
chmod +x "$SCRIPT_DIR/update_sports_dashboard.py"
chmod +x "$SCRIPT_DIR/update_gpu.sh"
chmod +x "$SCRIPT_DIR/starrupture_status.sh"
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
echo "     Sports updates:   every 30 minutes"

# ---------- 5. XDG autostart entries ----------
info "Setting up autostart entries..."

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/World Clock Conky.desktop" <<EOF
[Desktop Entry]
Type=Application
Exec=conky -d -c $CONKY_DIR/conky-clock.conf
X-GNOME-Autostart-enabled=true
NoDisplay=false
Hidden=false
Name[en_US]=World Clock Conky
Comment[en_US]=Conky clock and info dashboard (top-right)
X-GNOME-Autostart-Delay=3
EOF
ok "Autostart entry: World Clock Conky"

cat > "$AUTOSTART_DIR/System Conky.desktop" <<EOF
[Desktop Entry]
Type=Application
Exec=conky -d -c $CONKY_DIR/conky-system.conf
X-GNOME-Autostart-enabled=true
NoDisplay=false
Hidden=false
Name[en_US]=System Conky
Comment[en_US]=Conky system stats dashboard (below clock)
X-GNOME-Autostart-Delay=3
EOF
ok "Autostart entry: System Conky"

cat > "$AUTOSTART_DIR/Sports Conky.desktop" <<EOF
[Desktop Entry]
Type=Application
Exec=conky -d -c $CONKY_DIR/conky-sports.conf
X-GNOME-Autostart-enabled=true
NoDisplay=false
Hidden=false
Name[en_US]=Sports Conky
Comment[en_US]=Conky sports dashboard (middle panel)
X-GNOME-Autostart-Delay=3
EOF
ok "Autostart entry: Sports Conky"

# ---------- 6. Initial data fetch ----------
info "Running initial data fetch..."
mkdir -p "$HOME/.cache"

# Create sports bets config directory and sample file if needed
BETS_DIR="$HOME/.config/sports-bets"
BETS_FILE="$BETS_DIR/active_bets.json"
mkdir -p "$BETS_DIR"
if [ ! -f "$BETS_FILE" ]; then
    cat > "$BETS_FILE" <<'BETSEOF'
{
    "bets": [],
    "parlays": []
}
BETSEOF
    ok "Created empty bets config at $BETS_FILE"
    info "Add active bets to enable live tracking in conky"
else
    ok "Bets config already exists at $BETS_FILE"
fi

BANKROLL_FILE="$BETS_DIR/bankroll.json"
if [ ! -f "$BANKROLL_FILE" ]; then
    cat > "$BANKROLL_FILE" <<'BANKEOF'
{
    "starting_bankroll": 0,
    "total_deposited": 0,
    "current_balance": 0,
    "in_play": 0,
    "wins": 0,
    "losses": 0
}
BANKEOF
    ok "Created empty bankroll config at $BANKROLL_FILE"
else
    ok "Bankroll config already exists at $BANKROLL_FILE"
fi

if "$SCRIPT_DIR/update_weather.sh" 2>/dev/null; then
    ok "Weather data fetched"
else
    warn "Weather fetch failed — will retry on next cron run"
fi

if "$SCRIPT_DIR/update_celtics.sh" 2>/dev/null; then
    ok "Sports data fetched"
else
    warn "Sports fetch failed — will retry on next cron run (may fail in offseason)"
fi

# ---------- 7. Optionally start conky ----------
echo ""
read -rp "Start conky now? [Y/n] " ans
ans=${ans:-Y}
if [[ "$ans" =~ ^[Yy] ]]; then
    # Kill any existing conky instances
    killall conky 2>/dev/null || true
    sleep 1
    conky -c "$CONKY_DIR/conky-clock.conf" -d
    conky -c "$CONKY_DIR/conky-sports.conf" -d
    conky -c "$CONKY_DIR/conky-system.conf" -d
    ok "Conky started (conky-clock.conf + conky-sports.conf + conky-system.conf)"
else
    info "Skipped — start manually with:"
    echo "  conky -c $CONKY_DIR/conky-clock.conf -d"
    echo "  conky -c $CONKY_DIR/conky-sports.conf -d"
    echo "  conky -c $CONKY_DIR/conky-system.conf -d"
fi

echo ""
ok "Conky setup complete — all three panels will auto-start on login!"
echo ""
echo "Files:"
echo "  Configs:    $CONKY_DIR/conky-clock.conf"
echo "              $CONKY_DIR/conky-sports.conf"
echo "              $CONKY_DIR/conky-system.conf"
echo "  Autostart:  $AUTOSTART_DIR/World Clock Conky.desktop"
echo "              $AUTOSTART_DIR/Sports Conky.desktop"
echo "              $AUTOSTART_DIR/System Conky.desktop"
echo "  Scripts:    $SCRIPT_DIR/update_weather.sh"
echo "              $SCRIPT_DIR/update_celtics.sh"
echo "              $SCRIPT_DIR/update_sports.py"
echo "              $SCRIPT_DIR/update_sports_dashboard.py"
echo "  Bets:       $BETS_FILE"
echo "  Bankroll:   $BANKROLL_FILE"
echo "  Cache:      ~/.cache/weather.txt"
echo "              ~/.cache/celtics_record.txt"
echo "              ~/.cache/celtics_next.txt"
