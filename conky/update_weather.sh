#!/bin/bash

# Source config.env from repo root for default settings
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_ROOT/config.env" ]]; then
    # shellcheck source=../config.env
    source "$REPO_ROOT/config.env"
fi

OUT="$HOME/.cache/weather.txt"
mkdir -p "$HOME/.cache"

STATION="${WEATHER_STATION:?Set WEATHER_STATION in config.env}"
OBS_URL="https://api.weather.gov/stations/$STATION/observations/latest"

DATA=$(curl -fsS "$OBS_URL")
[ -z "$DATA" ] && exit 1

c_to_f() { awk '{printf "%.0f", ($1 * 9/5) + 32}'; }
kmh_to_mph() { awk '{printf "%.0f", $1 * 0.6214}'; }

deg_to_arrow() {
    deg=$1
    [ -z "$deg" ] || [ "$deg" = "null" ] && echo "?" && return
    arrows=("↑" "↗" "→" "↘" "↓" "↙" "←" "↖")
    index=$(( ( (deg + 22) / 45 ) % 8 ))
    echo "${arrows[$index]}"
}

# Nerd Font Weather Icons
get_icon() {
    cond=$(echo "$1" | tr '[:upper:]' '[:lower:]')

    if [[ $cond =~ thunder ]]; then
        echo ""   # thunderstorm
    elif [[ $cond =~ snow|blizzard|flurr ]]; then
        echo ""   # snow
    elif [[ $cond =~ rain|shower|drizzle|precip ]]; then
        echo ""   # rain
    elif [[ $cond =~ sleet|ice ]]; then
        echo ""   # sleet
    elif [[ $cond =~ fog|mist|haze ]]; then
        echo ""   # fog
    elif [[ $cond =~ cloudy ]]; then
        echo ""   # cloudy
    elif [[ $cond =~ clear|sunny ]]; then
        echo ""   # sunny
    else
        echo ""   # thermometer fallback
    fi
}

TEMP_C=$(echo "$DATA" | jq -r '.properties.temperature.value')
FEELS_C=$(echo "$DATA" | jq -r '.properties.windChill.value // .properties.heatIndex.value // .properties.temperature.value')
HUMIDITY=$(echo "$DATA" | jq -r '.properties.relativeHumidity.value' | awk '{printf "%.0f", $1}')
WIND_KMH=$(echo "$DATA" | jq -r '.properties.windSpeed.value')
WIND_DIR=$(echo "$DATA" | jq -r '.properties.windDirection.value')
COND=$(echo "$DATA" | jq -r '.properties.textDescription')

# Strip useless "Unknown Precipitation" entirely
[[ "$COND" =~ ^[Uu]nknown[[:space:]]+(.+) ]] && COND="${BASH_REMATCH[1]}"
[[ "${COND,,}" == "precipitation" ]] && COND=""
[ "$COND" = "null" ] || [ -z "$COND" ] && COND="N/A"

# Truncate long conditions to fit fixed-width widget
[ ${#COND} -gt 24 ] && COND="${COND:0:22}.."

[ "$TEMP_C" != "null" ] && TEMP_F=$(echo "$TEMP_C" | c_to_f)
[ "$FEELS_C" != "null" ] && FEELS_F=$(echo "$FEELS_C" | c_to_f)
[ "$WIND_KMH" != "null" ] && WIND_MPH=$(echo "$WIND_KMH" | kmh_to_mph)

TEMP_C_DISPLAY=${TEMP_C:+$(printf "%.0f" "$TEMP_C")}
WIND_ARROW=$(deg_to_arrow "$WIND_DIR")
ICON=$(get_icon "$COND")

# --- Get Today's Forecast High ---
LAT=$(echo "$DATA" | jq -r '.geometry.coordinates[1]')
LON=$(echo "$DATA" | jq -r '.geometry.coordinates[0]')

FORECAST_URL=$(curl -fsS "https://api.weather.gov/points/$LAT,$LON" | jq -r '.properties.forecast')
FORECAST_DATA=$(curl -fsS "$FORECAST_URL")

TODAY_HIGH=$(echo "$FORECAST_DATA" | jq -r '.properties.periods[0].temperature')

{
echo "$ICON  $COND"
echo "Temp:  ${TEMP_F:-N/A}°F / ${TEMP_C_DISPLAY:-N/A}°C (Feels ${FEELS_F:-N/A}°F)"
echo "High:  ${TODAY_HIGH:-N/A}°F"
echo "Humid: ${HUMIDITY:-N/A}%"
echo "Wind:  ${WIND_MPH:-N/A} mph $WIND_ARROW"
} > "$OUT"
