#!/usr/bin/env bash
# starrupture_status.sh — Reports the StarRupture dedicated server status
# for the conky system panel.
#
# Outputs a status word wrapped in conky color markup so the system panel
# can display it inline without nested if_match blocks.
#
#   online         green   — container running and docker healthcheck passing
#   starting       yellow  — container running, healthcheck still starting
#                            (Wine cold-boot ~30-60s)
#   unhealthy      red     — container running but healthcheck failing
#   restarting     yellow  — Docker is restarting the container
#   stopped        red     — container exists but isn't running
#   offline        grey    — container doesn't exist at all
#
# Set PLAIN=1 to skip the markup (useful when calling from a shell).
# Used by conky-system.conf via `execi 30`.

set -uo pipefail

CONTAINER=${CONTAINER:-starrupture}

# Inspect once to avoid two daemon calls. Empty output → container missing.
output=$(
    docker inspect \
        --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
        "$CONTAINER" 2>/dev/null
)

if [[ -z "$output" ]]; then
    state=missing
    health=missing
else
    read -r state health <<< "$output"
fi

case "$state" in
    running)
        case "$health" in
            healthy)   word=online;    color=green ;;
            starting)  word=starting;  color=yellow ;;
            unhealthy) word=unhealthy; color=red ;;
            none)      word=online;    color=green ;;  # no healthcheck → assume OK if running
            *)         word="$health"; color=red ;;
        esac
        ;;
    exited|dead|created)  word=stopped;    color=red ;;
    restarting)           word=restarting; color=yellow ;;
    paused)               word=paused;     color=yellow ;;
    missing)              word=offline;    color="#888888" ;;
    *)                    word="$state";   color=red ;;
esac

if [[ "${PLAIN:-0}" == "1" ]]; then
    echo "$word"
else
    echo "\${color $color}$word\${color}"
fi
