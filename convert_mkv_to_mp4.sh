#!/bin/bash

# ============================================================
# convert_mkv_to_mp4.sh
# Converts MKV files to MP4 (H.264/AAC) for Plex/ErsatzTV
# direct play compatibility on iPhone and other devices.
#
# Features:
#   - Stream copies video/audio if already compatible
#   - Re-encodes only what needs to change (saves time)
#   - Converts image-based subtitles to skip (can't embed in MP4)
#   - Preserves folder structure in output directory
#   - Skips already-converted files
#   - Logs all activity to a log file
#   - Shows progress and estimated completion
# ============================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helper functions ─────────────────────────────────────────
print_header() {
    echo -e "\n${BOLD}${CYAN}========================================${NC}"
    echo -e "${BOLD}${CYAN}   MKV → MP4 Converter for Plex/ErsatzTV${NC}"
    echo -e "${BOLD}${CYAN}========================================${NC}\n"
}

log() {
    local level="$1"
    local msg="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
    case "$level" in
        INFO)    echo -e "${GREEN}[INFO]${NC}  $msg" ;;
        WARN)    echo -e "${YELLOW}[WARN]${NC}  $msg" ;;
        ERROR)   echo -e "${RED}[ERROR]${NC} $msg" ;;
        SKIP)    echo -e "${CYAN}[SKIP]${NC}  $msg" ;;
    esac
}

format_size() {
    local bytes=$1
    if   (( bytes >= 1073741824 )); then printf "%.2f GB" "$(echo "scale=2; $bytes/1073741824" | bc)"
    elif (( bytes >= 1048576 ));    then printf "%.2f MB" "$(echo "scale=2; $bytes/1048576"    | bc)"
    else                                 printf "%d KB"   "$(( bytes / 1024 ))"
    fi
}

format_time() {
    local secs=$1
    printf "%02dh %02dm %02ds" "$(( secs/3600 ))" "$(( (secs%3600)/60 ))" "$(( secs%60 ))"
}

# ── Dependency check ─────────────────────────────────────────
check_deps() {
    local missing=()
    for cmd in ffmpeg ffprobe bc; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if (( ${#missing[@]} > 0 )); then
        echo -e "${RED}Missing required tools: ${missing[*]}${NC}"
        echo "Install with: sudo apt install ffmpeg bc"
        exit 1
    fi
}

# ── Detect best codec options for a file ────────────────────
# Populates globals: FFMPEG_ARGS (array) and CODEC_INFO (string)
FFMPEG_ARGS=()
CODEC_INFO=""

build_ffmpeg_args() {
    local input="$1"
    FFMPEG_ARGS=()

    local video_codec
    video_codec=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=codec_name -of default=nw=1:nk=1 "$input" 2>/dev/null)

    # Detect bit depth -- 10-bit input must be converted to yuv420p for libx264
    local pix_fmt bit_depth
    pix_fmt=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=pix_fmt -of default=nw=1:nk=1 "$input" 2>/dev/null)
    case "$pix_fmt" in
        *10le|*10be|yuv420p10*|yuv444p10*) bit_depth=10 ;;
        *) bit_depth=8 ;;
    esac

    # Video args — each flag is a separate array element (safe with any filename)
    case "$video_codec" in
        h264)
            if (( bit_depth == 10 )); then
                FFMPEG_ARGS+=(-c:v libx264 -crf 18 -preset medium -profile:v high -level 4.1 -pix_fmt yuv420p)
            else
                FFMPEG_ARGS+=(-c:v copy)
            fi
            ;;
        *)
            FFMPEG_ARGS+=(-c:v libx264 -crf 18 -preset medium -profile:v high -level 4.1)
            (( bit_depth == 10 )) && FFMPEG_ARGS+=(-pix_fmt yuv420p)
            ;;
    esac

    # Audio: check each track individually — copy AAC, re-encode everything else
    # This preserves ALL audio tracks (all languages, commentary, etc.)
    local audio_codecs=()
    mapfile -t audio_codecs < <(ffprobe -v error -select_streams a \
        -show_entries stream=codec_name -of default=nw=1:nk=1 "$input" 2>/dev/null)

    for idx in "${!audio_codecs[@]}"; do
        case "${audio_codecs[$idx]}" in
            aac) FFMPEG_ARGS+=(-c:a:${idx} copy) ;;
            *)   FFMPEG_ARGS+=(-c:a:${idx} aac -b:a:${idx} 192k) ;;
        esac
    done

    # Subtitles: strip entirely — MP4 image-based subs not supported
    FFMPEG_ARGS+=(-sn)

    local num_tracks=${#audio_codecs[@]}
    local all_codecs
    all_codecs=$(IFS='/'; echo "${audio_codecs[*]}")
    CODEC_INFO="$video_codec (${bit_depth}bit) | audio tracks: $num_tracks ($all_codecs)"
}

# ── Convert a single file ────────────────────────────────────
convert_file() {
    local input="$1"
    local output="$2"
    local current="$3"
    local total="$4"

    echo ""
    echo -e "${BOLD}[${current}/${total}]${NC} $(basename "$input")"

    # Get codec strategy — populates FFMPEG_ARGS array and CODEC_INFO string
    build_ffmpeg_args "$input"

    local input_size
    input_size=$(stat -c%s "$input")

    log INFO "Converting [$current/$total]: $(basename "$input") | codecs: $CODEC_INFO"

    # Create output directory if needed
    mkdir -p "$(dirname "$output")"

    # Run ffmpeg (suppress verbose output, show only errors + progress line)
    local start_time=$SECONDS
    if ffmpeg -hide_banner -loglevel error -stats \
        -i "$input" \
        "${FFMPEG_ARGS[@]}" \
        -movflags +faststart \
        -map 0:v:0 -map 0:a \
        "$output" 2>&1 | grep --line-buffered -E "^(frame|size|time|speed)" | \
        while IFS= read -r line; do printf "\r  ${CYAN}%-70s${NC}" "$line"; done
    then
        echo ""  # newline after progress
        local elapsed=$(( SECONDS - start_time ))
        local output_size
        output_size=$(stat -c%s "$output")
        local saved=$(( input_size - output_size ))

        log INFO "  Done in $(format_time $elapsed) | Input: $(format_size $input_size) → Output: $(format_size $output_size) | Saved: $(format_size $saved)"
        echo -e "  ${GREEN}✓ Done${NC} in $(format_time $elapsed) | $(format_size $input_size) → $(format_size $output_size)"

        TOTAL_INPUT_BYTES=$(( TOTAL_INPUT_BYTES + input_size ))
        TOTAL_OUTPUT_BYTES=$(( TOTAL_OUTPUT_BYTES + output_size ))
        (( CONVERTED++ )) || true
    else
        echo ""
        log ERROR "FFmpeg failed for: $input"
        echo -e "  ${RED}✗ Failed${NC} — check $LOG_FILE for details"
        rm -f "$output"   # remove partial output
        (( FAILED++ )) || true
    fi
}

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
print_header
check_deps

# ── Prompt: source folder ────────────────────────────────────
echo -e "${BOLD}Source folder${NC} (where your MKV files are):"
read -rp "  Path: " SOURCE_DIR
SOURCE_DIR="${SOURCE_DIR%/}"   # strip trailing slash

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo -e "${RED}Error: '$SOURCE_DIR' is not a valid directory.${NC}"
    exit 1
fi

# ── Prompt: output folder ────────────────────────────────────
echo ""
echo -e "${BOLD}Output folder${NC} (where MP4 files will be saved):"
read -rp "  Path: " OUTPUT_DIR
OUTPUT_DIR="${OUTPUT_DIR%/}"

if [[ -z "$OUTPUT_DIR" ]]; then
    echo -e "${RED}Error: Output folder cannot be empty.${NC}"
    exit 1
fi
mkdir -p "$OUTPUT_DIR"

# ── Log file ─────────────────────────────────────────────────
LOG_FILE="${OUTPUT_DIR}/conversion_$(date '+%Y%m%d_%H%M%S').log"
touch "$LOG_FILE"

# ── Disk space check ─────────────────────────────────────────
echo ""
AVAIL_BYTES=$(df --output=avail -B1 "$OUTPUT_DIR" | tail -1)
echo -e "${CYAN}Available space on output drive:${NC} $(format_size $AVAIL_BYTES)"
echo -e "${YELLOW}Tip:${NC} H.264/AAC re-encodes are typically 30–60% smaller than the original."
echo ""

# ── Confirm before starting ──────────────────────────────────
echo -e "  Source : ${BOLD}$SOURCE_DIR${NC}"
echo -e "  Output : ${BOLD}$OUTPUT_DIR${NC}"
echo -e "  Log    : ${BOLD}$LOG_FILE${NC}"
echo ""
read -rp "Proceed? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && echo "Aborted." && exit 0

# ── Find MKV files ───────────────────────────────────────────
echo ""
echo "Scanning for .mkv files..."
mapfile -t MKV_FILES < <(find "$SOURCE_DIR" -type f -iname "*.mkv" | sort)
TOTAL=${#MKV_FILES[@]}

if (( TOTAL == 0 )); then
    echo -e "${YELLOW}No .mkv files found in '$SOURCE_DIR'.${NC}"
    exit 0
fi

echo -e "Found ${BOLD}${TOTAL}${NC} MKV file(s).\n"
log INFO "Starting conversion of $TOTAL files | source: $SOURCE_DIR | output: $OUTPUT_DIR"

# ── Counters ─────────────────────────────────────────────────
CONVERTED=0
FAILED=0
SKIPPED=0
TOTAL_INPUT_BYTES=0
TOTAL_OUTPUT_BYTES=0
OVERALL_START=$SECONDS

# ── Process each file ────────────────────────────────────────
for i in "${!MKV_FILES[@]}"; do
    INPUT="${MKV_FILES[$i]}"
    # Preserve relative folder structure under output dir
    REL_PATH="${INPUT#$SOURCE_DIR/}"
    OUTPUT="${OUTPUT_DIR}/${REL_PATH%.mkv}.mp4"

    if [[ -f "$OUTPUT" ]]; then
        log SKIP "Already exists, skipping: $(basename "$INPUT")"
        echo -e "${CYAN}[SKIP]${NC}  $(basename "$INPUT") — output already exists"
        (( SKIPPED++ )) || true
        continue
    fi

    convert_file "$INPUT" "$OUTPUT" "$(( i + 1 ))" "$TOTAL"

    # Rough ETA after first file
    if (( CONVERTED == 1 && TOTAL > 1 )); then
        local_elapsed=$(( SECONDS - OVERALL_START ))
        remaining=$(( local_elapsed * (TOTAL - 1) ))
        echo -e "  ${CYAN}Estimated remaining:${NC} ~$(format_time $remaining) (rough estimate)"
    fi
done

# ── Summary ──────────────────────────────────────────────────
TOTAL_ELAPSED=$(( SECONDS - OVERALL_START ))
echo ""
echo -e "${BOLD}${CYAN}════════════════ Summary ════════════════${NC}"
echo -e "  Total files  : $TOTAL"
echo -e "  ${GREEN}Converted    : $CONVERTED${NC}"
echo -e "  ${CYAN}Skipped      : $SKIPPED${NC}"
echo -e "  ${RED}Failed       : $FAILED${NC}"
echo -e "  Total time   : $(format_time $TOTAL_ELAPSED)"
if (( CONVERTED > 0 )); then
    SAVED=$(( TOTAL_INPUT_BYTES - TOTAL_OUTPUT_BYTES ))
    echo -e "  Space saved  : $(format_size $SAVED) ($(format_size $TOTAL_INPUT_BYTES) → $(format_size $TOTAL_OUTPUT_BYTES))"
fi
echo -e "  Log file     : $LOG_FILE"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${NC}\n"

log INFO "Conversion complete | converted=$CONVERTED skipped=$SKIPPED failed=$FAILED elapsed=$(format_time $TOTAL_ELAPSED)"