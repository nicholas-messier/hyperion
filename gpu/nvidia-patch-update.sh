#!/bin/bash
# ============================================================
# nvidia-patch-update.sh
#
# Idempotent wrapper that ensures the keylase/nvidia-patch
# (NVENC session-limit removal) is applied to the currently
# running NVIDIA driver. Re-run after any driver upgrade.
#
# What the patch does:
#   Consumer NVIDIA cards (e.g. GTX 1050 Ti) limit concurrent
#   NVENC encode sessions to 3 in libnvidia-encode.so. The
#   keylase/nvidia-patch flips a single byte to remove that cap,
#   matching the behavior of Quadro/professional cards. NVDEC,
#   CUDA, and overall GPU functionality are unaffected.
#
# Usage:
#   sudo nvidia-patch-update.sh           # Apply (or re-apply) the patch
#   sudo nvidia-patch-update.sh --status  # Report current patch state
#   sudo nvidia-patch-update.sh --rollback  # Restore original library
#
# Exit codes:
#   0  patch applied (or already applied)
#   1  driver not supported / patch failed
#   2  nvidia-patch repo could not be cloned/updated
#
# Requires:
#   sudo, git, the NVIDIA driver installed, internet access
#   for cloning https://github.com/keylase/nvidia-patch
# ============================================================

set -euo pipefail

REPO_URL="https://github.com/keylase/nvidia-patch.git"
REPO_DIR="/opt/nvidia-patch"
ACTION="apply"

for arg in "$@"; do
    case "$arg" in
        --status)   ACTION="status" ;;
        --rollback) ACTION="rollback" ;;
        --apply|"") ACTION="apply" ;;
        -h|--help)
            sed -n '2,33p' "$0"
            exit 0 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Sudo guard ──────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (modifies /usr/lib/x86_64-linux-gnu/libnvidia-encode.so)."
    echo "Re-run with: sudo $0 $*"
    exit 1
fi

# ── Driver detection ────────────────────────────────────────
if ! command -v nvidia-smi >/dev/null; then
    echo "ERROR: nvidia-smi not found. Install the NVIDIA driver first."
    exit 1
fi
DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
echo "Detected GPU: $GPU_NAME"
echo "Driver version: $DRIVER_VERSION"

# ── Repo bootstrap / update ─────────────────────────────────
if [[ ! -d "$REPO_DIR" ]]; then
    echo "Cloning $REPO_URL -> $REPO_DIR ..."
    git clone --depth=1 "$REPO_URL" "$REPO_DIR" || { echo "Clone failed."; exit 2; }
else
    echo "Updating $REPO_DIR ..."
    git -C "$REPO_DIR" fetch --depth=1 origin master >/dev/null 2>&1 || true
    git -C "$REPO_DIR" reset --hard origin/master >/dev/null 2>&1 || true
fi

# ── Verify driver supported ─────────────────────────────────
if ! bash "$REPO_DIR/patch.sh" -c "$DRIVER_VERSION" >/dev/null 2>&1; then
    echo "ERROR: Driver $DRIVER_VERSION is not in the patch's supported list."
    echo "  Run \`bash $REPO_DIR/patch.sh -l\` to see all supported versions."
    exit 1
fi

# ── Status helper ───────────────────────────────────────────
LIB="/usr/lib/x86_64-linux-gnu/libnvidia-encode.so.${DRIVER_VERSION}"
BACKUP="/opt/nvidia/libnvidia-encode-backup/libnvidia-encode.so.${DRIVER_VERSION}"

print_status() {
    if [[ -f "$BACKUP" ]]; then
        local cur_sha bak_sha
        cur_sha=$(sha1sum "$LIB" | awk '{print $1}')
        bak_sha=$(sha1sum "$BACKUP" | awk '{print $1}')
        if [[ "$cur_sha" != "$bak_sha" ]]; then
            echo "Status: PATCHED (lib=$cur_sha, backup=$bak_sha)"
            return 0
        fi
        echo "Status: backup exists but lib matches it — NOT patched (or already rolled back)."
        return 1
    fi
    echo "Status: no backup present — NOT yet patched."
    return 1
}

# ── Dispatch ────────────────────────────────────────────────
case "$ACTION" in
    status)
        print_status || true
        ;;
    rollback)
        bash "$REPO_DIR/patch.sh" -r
        ;;
    apply)
        bash "$REPO_DIR/patch.sh"
        echo ""
        print_status || true
        ;;
esac
