#!/bin/bash
# conversion_status.sh — Reports which conversion pipeline scripts are active
# Used by conky-system.conf to display status on the desktop widget
#
# Detects: convert_mkv_to_mp4.sh, sync_converted.sh, verify_conversion.sh

scripts=()

if pgrep -f "convert_mkv_to_mp4\.sh" >/dev/null 2>&1; then
    jobs=$(pgrep -c ffmpeg 2>/dev/null || echo 0)
    if [ "$jobs" -gt 0 ]; then
        scripts+=("convert ($jobs jobs)")
    else
        scripts+=("convert")
    fi
fi

if pgrep -f "sync_converted\.sh" >/dev/null 2>&1; then
    scripts+=("sync")
fi

if pgrep -f "verify_conversion\.sh" >/dev/null 2>&1; then
    scripts+=("verify")
fi

if [ ${#scripts[@]} -eq 0 ]; then
    echo "idle"
else
    IFS=', '
    echo "active - ${scripts[*]}"
fi
