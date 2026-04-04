#!/bin/bash

OUT="$HOME/.cache/wttr_laconia.txt"
mkdir -p "$HOME/.cache"

STATION="KLCI"
OBS_URL="https://api.weather.gov/stations/$STATION/observations/latest"

DATA=$(curl -fsS "$OBS_URL")
[ -z "$DATA" ] && exit 1

c_to_f() { awk '{printf "%.0f", ($1 * 9/5) + 32}'; }
ms_to_mph() { awk '{printf "%.0f", $1 * 2.237}'; }

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
    elif [[ $cond =~ rain|shower|drizzle ]]; then
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
WIND_MS=$(echo "$DATA" | jq -r '.properties.windSpeed.value')
WIND_DIR=$(echo "$DATA" | jq -r '.properties.windDirection.value')
COND=$(echo "$DATA" | jq -r '.properties.textDescription')

[ "$TEMP_C" != "null" ] && TEMP_F=$(echo "$TEMP_C" | c_to_f)
[ "$FEELS_C" != "null" ] && FEELS_F=$(echo "$FEELS_C" | c_to_f)
[ "$WIND_MS" != "null" ] && WIND_MPH=$(echo "$WIND_MS" | ms_to_mph)

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
echo "$ICON  $COND  $ICON"
echo "Temp: ${TEMP_F:-N/A}°F / ${TEMP_C_DISPLAY:-N/A}°C (Feels ${FEELS_F:-N/A}°F)"
echo "High Today: ${TODAY_HIGH:-N/A}°F"
echo "Humidity: ${HUMIDITY:-N/A}%"
} > "$OUT"
