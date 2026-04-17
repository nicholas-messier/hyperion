#!/bin/bash
# =============================================================
# archive.sh
# Nightly sync between local drives + optional external export
#
# Usage:
#   ./archive.sh              # Local sync only (for cron)
#   ./archive.sh --export     # Local sync + copy to external drive
# =============================================================

set -euo pipefail

# Source config.env from repo root for default paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_ROOT/config.env" ]]; then
    # shellcheck source=../config.env
    source "$REPO_ROOT/config.env"
fi

# -- Configuration ---------------------------------------------
SOURCE="${BACKUP_SOURCE:-/data/}"
STAGING="${BACKUP_STAGING:-/archive/nicks_data}"
ARCHIVE_DIR="$(dirname "$STAGING")"
EXTERNAL_DEV="${EXTERNAL_DRIVE_DEV:-/dev/sda2}"
MOUNT_POINT="${EXTERNAL_DRIVE_MOUNT:-/mnt/external}"
EXTERNAL_TARGET="${BACKUP_EXTERNAL_TARGET:-$MOUNT_POINT/nicks_data_backup}"
LOG_DIR="${BACKUP_LOG_DIR:-/var/log/archive}"
LOG_FILE="$LOG_DIR/archive_$(date '+%Y-%m-%d').log"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

EXPORT=false

# -- Colors (disabled when running in cron/non-interactive) ----
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' RED='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# -- Parse arguments -------------------------------------------
for arg in "$@"; do
    case $arg in
        --export) EXPORT=true ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# -- Logging ---------------------------------------------------
mkdir -p "$LOG_DIR"

log() {
    local level="$1"
    local msg="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" | tee -a "$LOG_FILE"
}

log_color() {
    local color="$1"
    local msg="$2"
    echo -e "${color}${msg}${NC}"
}

# -- Cleanup/trap ----------------------------------------------
MOUNTED_BY_US=false

cleanup() {
    local exit_code=$?
    if $MOUNTED_BY_US && mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        log "INFO" "Unmounting external drive..."
        sudo umount "$MOUNT_POINT" && log "INFO" "External drive unmounted cleanly." \
            || log "WARN" "Failed to unmount $MOUNT_POINT — unmount manually when safe."
    fi
    if (( exit_code != 0 )); then
        log "ERROR" "Script exited with error code $exit_code. Check log: $LOG_FILE"
    fi
    # Prune old logs
    find "$LOG_DIR" -name "archive_*.log" -mtime +${RETENTION_DAYS} -delete 2>/dev/null || true
}
trap cleanup EXIT

# -- Start -----------------------------------------------------
START_TIME=$SECONDS
log "INFO" "========================================"
log "INFO" "Archive job started | export=$EXPORT"
log "INFO" "Source: $SOURCE"
log "INFO" "Staging: $STAGING"

# -- Ensure directories exist ----------------------------------
mkdir -p "$STAGING" "$ARCHIVE_DIR"

# -- Local sync ------------------------------------------------
log_color "$CYAN" "[*] Syncing $SOURCE --> $STAGING ..."
log "INFO" "Starting local rsync..."

# --delete-before: deletes removed files first, then transfers new ones
# --log-file: rsync writes its own transfer log alongside ours
if rsync -a --delete-before \
    --log-file="$LOG_DIR/rsync_local_$(date '+%Y-%m-%d').log" \
    "$SOURCE" "$STAGING" >> "$LOG_FILE" 2>&1; then
    log "INFO" "Local sync complete: $STAGING"
    log_color "$GREEN" "[OK] Local sync complete."
else
    log "ERROR" "Local rsync failed!"
    log_color "$RED" "[ERROR] Local rsync failed — check $LOG_FILE"
    exit 1
fi

# -- External export (--export flag only) ----------------------
if $EXPORT; then
    log "INFO" "----------------------------------------"
    log "INFO" "Starting external export to $EXTERNAL_TARGET"
    log_color "$CYAN" "[*] Exporting to external drive..."

    # Ensure mount point exists
    sudo mkdir -p "$MOUNT_POINT"

    # Mount if not already mounted
    if ! mountpoint -q "$MOUNT_POINT"; then
        log "INFO" "Mounting $EXTERNAL_DEV to $MOUNT_POINT..."
        log_color "$CYAN" "[*] Mounting external drive..."
        if sudo mount "$EXTERNAL_DEV" "$MOUNT_POINT"; then
            MOUNTED_BY_US=true
            log "INFO" "External drive mounted successfully."
        else
            log "ERROR" "Failed to mount $EXTERNAL_DEV — is the drive connected?"
            log_color "$RED" "[ERROR] Mount failed. Is the Seagate plugged in?"
            exit 1
        fi
    else
        log "INFO" "$MOUNT_POINT already mounted."
        log_color "$GREEN" "[OK] External drive already mounted."
    fi

    # Check available space before syncing
    # Account for space already used by existing target (rsync --delete-before frees it first)
    AVAIL_BYTES=$(df --output=avail -B1 "$MOUNT_POINT" | tail -1)
    TARGET_BYTES=0
    if [[ -d "$EXTERNAL_TARGET" ]]; then
        TARGET_BYTES=$(du -sb "$EXTERNAL_TARGET" | cut -f1)
    fi
    EFFECTIVE_AVAIL=$(( AVAIL_BYTES + TARGET_BYTES ))
    SOURCE_BYTES=$(du -sb "$STAGING" | cut -f1)
    if (( SOURCE_BYTES > EFFECTIVE_AVAIL )); then
        log "ERROR" "Not enough space on external drive! Need $(( SOURCE_BYTES / 1073741824 ))GB, have $(( EFFECTIVE_AVAIL / 1073741824 ))GB effective ($(( AVAIL_BYTES / 1073741824 ))GB free + $(( TARGET_BYTES / 1073741824 ))GB reclaimable)"
        log_color "$RED" "[ERROR] Not enough space on external drive!"
        exit 1
    fi

    # Ensure target directory exists
    mkdir -p "$EXTERNAL_TARGET"

    # Rsync to external — no --progress in log mode (too noisy)
    # Use --info=progress2 only when running interactively
    RSYNC_FLAGS="-ah --delete-before --no-owner --no-group"
    if [ -t 1 ]; then
        RSYNC_FLAGS="$RSYNC_FLAGS --info=progress2"
    fi

    if rsync $RSYNC_FLAGS \
        --log-file="$LOG_DIR/rsync_external_$(date '+%Y-%m-%d').log" \
        "$STAGING/" "$EXTERNAL_TARGET/" >> "$LOG_FILE" 2>&1; then
        log "INFO" "External export complete: $EXTERNAL_TARGET"
        log_color "$GREEN" "[OK] External export complete."
    else
        log "ERROR" "External rsync failed!"
        log_color "$RED" "[ERROR] External rsync failed — check $LOG_FILE"
        exit 1
    fi
fi

# -- Summary ---------------------------------------------------
ELAPSED=$(( SECONDS - START_TIME ))
MINS=$(( ELAPSED / 60 ))
SECS=$(( ELAPSED % 60 ))
log "INFO" "Archive job finished in ${MINS}m ${SECS}s"
log "INFO" "========================================"
log_color "$GREEN" "[DONE] Archive complete in ${MINS}m ${SECS}s. Log: $LOG_FILE"