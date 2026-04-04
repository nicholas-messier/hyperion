#!/bin/bash
# update_celtics.sh — Fetch next Boston Celtics game from ESPN API
# Writes formatted output to ~/.cache/celtics_next.txt
# Checks today's scoreboard first (live/upcoming today), then the full schedule.

OUT="$HOME/.cache/celtics_next.txt"
mkdir -p "$HOME/.cache"

TEAM="BOS"
SCOREBOARD_URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SCHEDULE_URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/${TEAM}/schedule"
TEAM_URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/${TEAM}"

# Fetch win-loss record
RECORD=$(curl -fsS "$TEAM_URL" 2>/dev/null | jq -r '.team.record.items[0].summary // empty' 2>/dev/null)
echo "${RECORD:-?}" > "$HOME/.cache/celtics_record.txt"

# Check today's scoreboard first (catches live and upcoming-today games)
GAME=$(curl -fsS "$SCOREBOARD_URL" 2>/dev/null | jq -r --arg team "$TEAM" '
    [.events[] | select(.competitions[0].competitors[].team.abbreviation == $team)] | .[0] // empty |
    {
        date: .date,
        status: .competitions[0].status.type.name,
        detail: .competitions[0].status.type.shortDetail,
        venue: .competitions[0].venue.fullName,
        city: (.competitions[0].venue.address.city + ", " + .competitions[0].venue.address.state),
        opponent: ([.competitions[0].competitors[] | select(.team.abbreviation != $team)][0].team.displayName),
        homeAway: ([.competitions[0].competitors[] | select(.team.abbreviation == $team)][0].homeAway)
    }' 2>/dev/null)

# If no game today or today's game is final, check the schedule for next upcoming
STATUS=$(echo "$GAME" | jq -r '.status // empty' 2>/dev/null)
if [ -z "$GAME" ] || [ "$STATUS" = "STATUS_FINAL" ]; then
    GAME=$(curl -fsS "$SCHEDULE_URL" 2>/dev/null | jq -r --arg team "$TEAM" '
        [.events[] | select(.competitions[0].status.type.name == "STATUS_SCHEDULED")] | .[0] // empty |
        {
            date: .date,
            status: .competitions[0].status.type.name,
            detail: "Scheduled",
            venue: .competitions[0].venue.fullName,
            city: (.competitions[0].venue.address.city + ", " + .competitions[0].venue.address.state),
            opponent: ([.competitions[0].competitors[] | select(.team.abbreviation != $team)][0].team.displayName),
            homeAway: ([.competitions[0].competitors[] | select(.team.abbreviation == $team)][0].homeAway)
        }' 2>/dev/null)
fi

if [ -z "$GAME" ] || [ "$GAME" = "null" ]; then
    echo "No upcoming games found" > "$OUT"
    exit 0
fi

OPPONENT=$(echo "$GAME" | jq -r '.opponent')
HOME_AWAY=$(echo "$GAME" | jq -r '.homeAway')
UTC_DATE=$(echo "$GAME" | jq -r '.date')
VENUE=$(echo "$GAME" | jq -r '.venue')
CITY=$(echo "$GAME" | jq -r '.city')
STATUS=$(echo "$GAME" | jq -r '.status')
DETAIL=$(echo "$GAME" | jq -r '.detail')

# Format: "vs" for home, "@" for away
if [ "$HOME_AWAY" = "home" ]; then
    MATCHUP="vs $OPPONENT"
else
    MATCHUP="@ $OPPONENT"
fi

# Convert UTC to local time
GAME_TIME=$(date -d "$UTC_DATE" '+%a %b %d  %I:%M %p' 2>/dev/null)

# Build output based on game status
if [ "$STATUS" = "STATUS_IN_PROGRESS" ]; then
    {
        echo "LIVE: Celtics $MATCHUP"
        echo "$VENUE — $CITY"
    } > "$OUT"
elif [ "$STATUS" = "STATUS_SCHEDULED" ]; then
    {
        echo "Celtics $MATCHUP"
        echo "$GAME_TIME"
        echo "$VENUE — $CITY"
    } > "$OUT"
else
    {
        echo "Celtics $MATCHUP"
        echo "$GAME_TIME"
        echo "$VENUE — $CITY"
    } > "$OUT"
fi
