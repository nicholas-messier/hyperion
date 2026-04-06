#!/bin/bash
# =============================================================
# setup_cron.sh
# Installs the nightly archive cron job for archive.sh
# Run this once: sudo bash setup_cron.sh
# =============================================================
 
SCRIPT_PATH="$(realpath archive.sh)"
CRON_TIME="0 2 * * *"   # 2:00 AM every night
CRON_USER="root"
CRON_LOG="/var/log/archive/cron.log"
CRON_LINE="$CRON_TIME $SCRIPT_PATH >> $CRON_LOG 2>&1"
 
# Must be run as root (needed for mount permissions)
if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo bash setup_cron.sh"
    exit 1
fi
 
# Make sure archive.sh exists and is executable
if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "ERROR: archive.sh not found at $SCRIPT_PATH"
    echo "Make sure setup_cron.sh is in the same directory as archive.sh"
    exit 1
fi
 
chmod +x "$SCRIPT_PATH"
mkdir -p /var/log/archive
 
# Check if cron job already exists
if crontab -u "$CRON_USER" -l 2>/dev/null | grep -qF "$SCRIPT_PATH"; then
    echo "Cron job already exists:"
    crontab -u "$CRON_USER" -l | grep "$SCRIPT_PATH"
    read -rp "Replace it? [y/N]: " CONFIRM
    [[ "${CONFIRM,,}" != "y" ]] && echo "Aborted." && exit 0
    # Remove existing entry
    crontab -u "$CRON_USER" -l 2>/dev/null | grep -vF "$SCRIPT_PATH" | crontab -u "$CRON_USER" -
fi
 
# Install cron job
( crontab -u "$CRON_USER" -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -u "$CRON_USER" -
 
echo ""
echo "Cron job installed successfully!"
echo ""
echo "  Schedule : Every night at 2:00 AM"
echo "  Script   : $SCRIPT_PATH"
echo "  Cron log : $CRON_LOG"
echo "  Job logs : /var/log/archive/archive_YYYY-MM-DD.log"
echo ""
echo "To verify:"
echo "  sudo crontab -l"
echo ""
echo "To run manually:"
echo "  sudo bash $SCRIPT_PATH              # local sync only"
echo "  sudo bash $SCRIPT_PATH --export     # sync + copy to Seagate"
echo ""
echo "To remove the cron job:"
echo "  sudo crontab -e"
