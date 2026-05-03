#!/bin/bash
# ============================================================
# nvenc-session-test.sh
#
# Spawn N concurrent ffmpeg h264_nvenc processes against the
# GPU and report how many succeed. With keylase/nvidia-patch
# applied a GTX 1050 Ti can sustain >3 sessions; without it
# the 4th fails with "OpenEncodeSessionEx failed: out of memory
# (10): (no details)".
#
# Usage:
#   ./nvenc-session-test.sh           # Test 5 concurrent sessions
#   ./nvenc-session-test.sh 8         # Test 8 concurrent sessions
#
# This is a smoke test. Real sessions consume more VRAM and
# encoder bandwidth than this synthetic test.
# ============================================================

set -euo pipefail

N="${1:-5}"
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR; pkill -P $$ ffmpeg 2>/dev/null || true" EXIT

if ! command -v nvidia-smi >/dev/null; then
    echo "ERROR: nvidia-smi not found. Install the NVIDIA driver first."
    exit 1
fi

echo "Spawning $N concurrent NVENC sessions..."
PIDS=()
for i in $(seq 1 "$N"); do
    ffmpeg -nostdin -hide_banner -loglevel error \
        -f lavfi -i "testsrc=size=1280x720:rate=30:duration=20" \
        -c:v h264_nvenc -preset p4 -profile:v high \
        -f null - >"$TMPDIR/out_$i.log" 2>"$TMPDIR/err_$i.log" &
    PIDS+=($!)
done

# Let them spin up
sleep 3

ENC_UTIL=$(nvidia-smi --query-gpu=utilization.encoder --format=csv,noheader,nounits | head -1)
SESSIONS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -c . || echo 0)
echo "After 3s: encoder util=${ENC_UTIL}%, compute apps=${SESSIONS}"

# Wait for all to finish
SUCCESS=0
FAIL=0
for pid in "${PIDS[@]}"; do
    if wait "$pid"; then
        ((SUCCESS++)) || true
    else
        ((FAIL++)) || true
    fi
done

echo ""
echo "Results: ${SUCCESS}/${N} sessions succeeded, ${FAIL} failed"

if (( FAIL > 0 )); then
    echo ""
    echo "Failure samples (first 5 lines of each error log that has content):"
    for f in "$TMPDIR"/err_*.log; do
        if [[ -s "$f" ]]; then
            echo "  --- $(basename "$f") ---"
            head -5 "$f" | sed 's/^/    /'
        fi
    done
    echo ""
    echo "If you see 'OpenEncodeSessionEx failed: out of memory (10)', the consumer"
    echo "session limit is hit. Apply nvidia-patch:"
    echo "  sudo $(dirname "$0")/nvidia-patch-update.sh"
fi
