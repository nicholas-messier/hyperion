#!/bin/bash
# update_gpu.sh — Cache NVIDIA GPU stats for the conky panel
#
# Runs nvidia-smi once and writes single-value cache files under ~/.cache/.
# The conky-system.conf reads each cache file with `${cat …}` so the panel
# refresh never blocks on nvidia-smi (and we only fork it once per update).
#
# Designed to be called by a conky `${execi 5 …}` wrapper (every 5s).
# If nvidia-smi is unavailable, the cache files are written with "n/a" so
# conky displays a clear placeholder instead of empty space.

set -euo pipefail

CACHE_DIR="${HOME}/.cache"
mkdir -p "$CACHE_DIR"

write_na() {
    for f in gpu_name gpu_temp gpu_util gpu_enc gpu_dec gpu_vram gpu_pwr; do
        echo "n/a" > "$CACHE_DIR/$f"
    done
}

if ! command -v nvidia-smi >/dev/null 2>&1; then
    write_na
    exit 0
fi

# One nvidia-smi call. The GPU name itself contains spaces ("NVIDIA GeForce
# GTX 1050 Ti"), so we cannot split on whitespace — split each comma-separated
# field onto its own line and read into an array.
mapfile -t FIELDS < <(
    nvidia-smi \
        --query-gpu=name,temperature.gpu,utilization.gpu,utilization.encoder,utilization.decoder,memory.used,memory.total,power.draw,power.limit \
        --format=csv,noheader,nounits 2>/dev/null \
        | head -1 \
        | awk -F',' '{ for (i=1; i<=NF; i++) { gsub(/^ *| *$/,"",$i); print $i } }'
)

if (( ${#FIELDS[@]} < 7 )); then
    write_na
    exit 0
fi

NAME="${FIELDS[0]}"
TEMP="${FIELDS[1]}"
UTIL="${FIELDS[2]}"
ENC="${FIELDS[3]}"
DEC="${FIELDS[4]}"
MEM_USED="${FIELDS[5]}"
MEM_TOTAL="${FIELDS[6]}"
POWER="${FIELDS[7]:-}"
PWR_LIMIT="${FIELDS[8]:-}"

# If nvidia-smi succeeded but returned nothing (no driver), fall back to n/a.
if [[ -z "${NAME:-}" ]]; then
    write_na
    exit 0
fi

# Strip the leading "NVIDIA " from the model so the line fits the panel width.
NAME="${NAME#NVIDIA }"

# Some fields may be "[Not Supported]" on certain SKUs — leave as-is for visibility.
echo "$NAME"          > "$CACHE_DIR/gpu_name"
# Match the CPU sensors() output format ("52.0°C") so both temps render the same
# way when shown side-by-side in conky.
printf '%s.0\xc2\xb0C\n' "$TEMP" > "$CACHE_DIR/gpu_temp"
echo "${UTIL}%"       > "$CACHE_DIR/gpu_util"
echo "${ENC}%"        > "$CACHE_DIR/gpu_enc"
echo "${DEC}%"        > "$CACHE_DIR/gpu_dec"
echo "${MEM_USED} / ${MEM_TOTAL} MiB" > "$CACHE_DIR/gpu_vram"

# Power may be "[Not Supported]" on cards without telemetry; only show if both work.
if [[ "$POWER" =~ ^[0-9]+(\.[0-9]+)?$ && "$PWR_LIMIT" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    printf "%.0f / %.0f W\n" "$POWER" "$PWR_LIMIT" > "$CACHE_DIR/gpu_pwr"
else
    echo "n/a" > "$CACHE_DIR/gpu_pwr"
fi
