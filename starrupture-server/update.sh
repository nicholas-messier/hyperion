#!/usr/bin/env bash
# update.sh — install or update the StarRupture dedicated server files
#
# The bundled SteamCMD inside indifferentbroccoli/starrupture-server-docker
# is broken (it tries to write to /root, which isn't writable when running
# as the steam user) and fails with "Missing configuration". So we run
# SteamCMD ourselves from the official steamcmd/steamcmd:ubuntu-22 image
# with a writable HOME, then mount the resulting files into the server
# container with UPDATE_ON_START=false.
#
# Anonymous login works fine for this — no Steam account credentials needed.
#
# Usage:
#   ./update.sh            # install or update server files
#   ./update.sh --no-stop  # don't stop the running server first

set -euo pipefail
cd "$(dirname "$0")"

STOP_SERVER=true
for arg in "$@"; do
    case "$arg" in
        --no-stop) STOP_SERVER=false ;;
        -h|--help)
            sed -n '2,18p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

if [[ ! -f .env ]]; then
    echo "ERROR: .env not found. Copy .env.example to .env first." >&2
    exit 1
fi

if grep -q '^ADMIN_PASSWORD=CHANGE_ME_BEFORE_FIRST_START' .env; then
    echo "WARNING: ADMIN_PASSWORD is still the placeholder in .env." >&2
    echo "Generate a strong one with:  openssl rand -base64 24" >&2
    echo "Then edit .env. Continuing the install anyway..." >&2
    echo
fi

mkdir -p server-files .steamcmd-state

# Stop the running server so SteamCMD can write freely
if [[ "$STOP_SERVER" == "true" ]]; then
    if docker compose ps --status=running --services 2>/dev/null | grep -q '^starrupture$'; then
        echo "Stopping running starrupture container..."
        docker compose stop starrupture
        STARTED_STOPPED=true
    fi
fi

UID_GID="$(id -u):$(id -g)"

echo
echo "─────────────────────────────────────────────────────────────"
echo "Running SteamCMD (anonymous) to install/update App 3809400"
echo "  Target dir:    $PWD/server-files"
echo "  SteamCMD home: $PWD/.steamcmd-state"
echo "  Run as:        $UID_GID  (so files are owned by host user)"
echo "─────────────────────────────────────────────────────────────"
echo

# Pull the steamcmd image once if missing (small, ~150 MB)
docker pull steamcmd/steamcmd:ubuntu-22 >/dev/null

# Notes on the invocation:
#  --user $UID_GID    so downloaded files end up owned by the host user
#  -e HOME=/state     override HOME so steamcmd has somewhere writable
#                     (its default is /root, which UID 1000 can't write to)
#  --entrypoint bash  bypass the image's broken default entrypoint that
#                     also tries to write to /root
#  +@sSteamCmdForcePlatformType windows
#                     StarRupture only ships a Windows server binary
docker run --rm -i \
    --user "$UID_GID" \
    -e HOME=/state \
    -v "$PWD/.steamcmd-state:/state" \
    -v "$PWD/server-files:/data" \
    --entrypoint bash \
    steamcmd/steamcmd:ubuntu-22 \
    -c 'steamcmd \
        +@sSteamCmdForcePlatformType windows \
        +force_install_dir /data \
        +login anonymous \
        +app_update 3809400 validate \
        +quit'

EXPECTED_EXE="server-files/StarRupture/Binaries/Win64/StarRuptureServerEOS-Win64-Shipping.exe"
if [[ -f "$EXPECTED_EXE" ]]; then
    echo
    echo "Server binary present: $EXPECTED_EXE"
    echo "Total install size:    $(du -sh server-files/ | cut -f1)"
else
    echo "ERROR: Server binary not found at $EXPECTED_EXE" >&2
    echo "Check the SteamCMD output above for the actual error." >&2
    exit 1
fi

# Restart if we stopped it
if [[ "${STARTED_STOPPED:-false}" == "true" ]]; then
    echo
    echo "Restarting starrupture container..."
    docker compose up -d
    echo "Tail logs with:  docker compose logs -f starrupture"
fi
