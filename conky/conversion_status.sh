#!/bin/bash
# conversion_status.sh — Reports which conversion pipeline scripts are active
# Used by conky-system.conf to display status on the desktop widget
#
# Detects: convert_mkv_to_mp4.sh, process_shared.sh, sync_converted.sh, verify_conversion.sh
#
# Uses pgrep -af with grep -v to exclude false positives from tmux
# session args that contain script names after the job has finished.

scripts=()

if pgrep -af "convert_mkv_to_mp4\.sh" 2>/dev/null | grep -qv "tmux"; then
    jobs=$(pgrep -c ffmpeg 2>/dev/null || echo 0)
    if [ "$jobs" -gt 0 ]; then
        scripts+=("convert ($jobs jobs)")
    else
        scripts+=("convert")
    fi
fi

if pgrep -af "process_shared\.sh" 2>/dev/null | grep -qv "tmux"; then
    scripts+=("shared")
fi

if pgrep -af "sync_converted\.sh" 2>/dev/null | grep -qv "tmux"; then
    scripts+=("sync")
fi

if pgrep -af "verify_conversion\.sh" 2>/dev/null | grep -qv "tmux"; then
    scripts+=("verify")
fi

if [ ${#scripts[@]} -eq 0 ]; then
    echo "idle"
else
    IFS=', '
    echo "active - ${scripts[*]}"
fi
