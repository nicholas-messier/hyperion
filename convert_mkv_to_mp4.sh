#!/bin/bash

# ============================================================
# convert_mkv_to_mp4.sh
# Converts MKV files to MP4 (H.264/AAC) for Plex/ErsatzTV
# direct play compatibility on iPhone and other devices.
#
# Usage:
#   ./convert_mkv_to_mp4.sh                        # Normal run, medium preset
#   ./convert_mkv_to_mp4.sh --preset=fast          # Faster encode
#   ./convert_mkv_to_mp4.sh --preset=slow          # Smallest files
#   ./convert_mkv_to_mp4.sh --plan                 # Generate ~12hr chunk files (default)
#   ./convert_mkv_to_mp4.sh --plan --hours=8          # Generate ~8hr chunk files
#   ./convert_mkv_to_mp4.sh --chunk=1              # Run only chunk 1
#   ./convert_mkv_to_mp4.sh --chunk=2 --preset=fast
#
# Features:
#   - Stream copies video/audio if already compatible (very fast)
#   - Re-encodes only what needs to change
#   - Handles 10-bit HEVC/H.265 correctly
#   - Preserves ALL audio tracks (all languages, commentary, etc.)
#   - Preserves folder structure in output directory
#   - Skips already-converted files (safe to resume)
#   - Rolling ETA updated after every file
#   - Chunk planner splits large libraries into ~1-day runs
#     without ever breaking a series mid-way through
#   - Full log written to output directory
# ============================================================

set -euo pipefail

# ── Parse arguments ──────────────────────────────────────────
PRESET="medium"
PLAN_MODE=false
CHUNK_HOURS=12
CHUNK_NUM=0

for arg in "$@"; do
    case $arg in
        --preset=*)
            PRESET="${arg#--preset=}"
            case "$PRESET" in
                fast|medium|slow) ;;
                *) echo "Invalid preset '$PRESET'. Use: fast, medium, or slow."; exit 1 ;;
            esac
            ;;
        --plan)
            PLAN_MODE=true
            ;;
        --hours=*)
            CHUNK_HOURS="${arg#--hours=}"
            if ! [[ "$CHUNK_HOURS" =~ ^[0-9]+$ ]] || (( CHUNK_HOURS < 1 )); then
                echo "Invalid hours value. Must be a positive integer."
                exit 1
            fi
            ;;
        --chunk=*)
            CHUNK_NUM="${arg#--chunk=}"
            if ! [[ "$CHUNK_NUM" =~ ^[0-9]+$ ]] || (( CHUNK_NUM < 1 )); then
                echo "Invalid chunk number. Must be a positive integer."
                exit 1
            fi
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--preset=fast|medium|slow] [--plan] [--hours=N] [--chunk=N]"
            exit 1
            ;;
    esac
done

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Globals ──────────────────────────────────────────────────
LOG_FILE=""
SOURCE_DIR=""
OUTPUT_DIR=""
FFMPEG_ARGS=()
CODEC_INFO=""
CONVERTED=0
FAILED=0
SKIPPED=0
TOTAL_INPUT_BYTES=0
TOTAL_OUTPUT_BYTES=0
TOTAL_FILE_SECS=0

# ── Print header ─────────────────────────────────────────────
print_header() {
    echo -e "\n${BOLD}${CYAN}=========================================${NC}"
    echo -e "${BOLD}${CYAN}   MKV -> MP4 Converter for Plex/ErsatzTV${NC}"
    echo -e "${BOLD}${CYAN}=========================================${NC}"
    echo -e "  Preset : ${BOLD}$PRESET${NC}"
    if $PLAN_MODE; then
        echo -e "  Mode   : ${BOLD}Chunk planning (~${CHUNK_HOURS}hr chunks)${NC}"
    elif (( CHUNK_NUM > 0 )); then
        echo -e "  Mode   : ${BOLD}Run chunk $CHUNK_NUM${NC}"
    fi
    echo ""
}

# ── Logging ──────────────────────────────────────────────────
log() {
    local level="$1" msg="$2" timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
    case "$level" in
        INFO)  echo -e "${GREEN}[INFO]${NC}  $msg" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC}  $msg" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} $msg" ;;
        SKIP)  echo -e "${CYAN}[SKIP]${NC}  $msg" ;;
    esac
}

# ── Format helpers ───────────────────────────────────────────
format_size() {
    local bytes=$1
    if   (( bytes >= 1073741824 )); then printf "%.2f GB" "$(echo "scale=2; $bytes/1073741824" | bc)"
    elif (( bytes >= 1048576 ));    then printf "%.2f MB" "$(echo "scale=2; $bytes/1048576"    | bc)"
    else                                 printf "%d KB"   "$(( bytes / 1024 ))"
    fi
}

format_time() {
    local secs=$1
    if   (( secs >= 86400 )); then
        printf "%dd %02dh %02dm" "$(( secs/86400 ))" "$(( (secs%86400)/3600 ))" "$(( (secs%3600)/60 ))"
    elif (( secs >= 3600 )); then
        printf "%02dh %02dm %02ds" "$(( secs/3600 ))" "$(( (secs%3600)/60 ))" "$(( secs%60 ))"
    else
        printf "%02dm %02ds" "$(( secs/60 ))" "$(( secs%60 ))"
    fi
}

# ── Get series name (top-level folder under SOURCE_DIR) ──────
get_series() {
    local rel="${1#${SOURCE_DIR}/}"
    echo "${rel%%/*}"
}

# ── Dependency check ─────────────────────────────────────────
check_deps() {
    local missing=()
    for cmd in ffmpeg ffprobe bc; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if (( ${#missing[@]} > 0 )); then
        echo -e "${RED}Missing: ${missing[*]}${NC} — install with: sudo apt install ffmpeg bc"
        exit 1
    fi
}

# ── Build ffmpeg args for a file ─────────────────────────────
# Sets globals: FFMPEG_ARGS (array), CODEC_INFO (string)
build_ffmpeg_args() {
    local input="$1"
    FFMPEG_ARGS=()

    local video_codec pix_fmt bit_depth
    video_codec=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=codec_name -of default=nw=1:nk=1 "$input" 2>/dev/null)
    pix_fmt=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=pix_fmt -of default=nw=1:nk=1 "$input" 2>/dev/null)

    case "$pix_fmt" in
        *10le|*10be|yuv420p10*|yuv444p10*) bit_depth=10 ;;
        *) bit_depth=8 ;;
    esac

    # Video: copy H.264 8-bit as-is; re-encode everything else
    case "$video_codec" in
        h264)
            if (( bit_depth == 10 )); then
                FFMPEG_ARGS+=(-c:v libx264 -crf 18 -preset "$PRESET" -profile:v high -level 4.1 -pix_fmt yuv420p)
            else
                FFMPEG_ARGS+=(-c:v copy)
            fi
            ;;
        *)
            FFMPEG_ARGS+=(-c:v libx264 -crf 18 -preset "$PRESET" -profile:v high -level 4.1)
            (( bit_depth == 10 )) && FFMPEG_ARGS+=(-pix_fmt yuv420p)
            ;;
    esac

    # Audio: per-track — copy AAC, re-encode everything else
    # All tracks preserved (all languages, commentary, etc.)
    local audio_codecs=()
    mapfile -t audio_codecs < <(ffprobe -v error -select_streams a \
        -show_entries stream=codec_name -of default=nw=1:nk=1 "$input" 2>/dev/null)

    for idx in "${!audio_codecs[@]}"; do
        case "${audio_codecs[$idx]}" in
            aac) FFMPEG_ARGS+=(-c:a:${idx} copy) ;;
            *)   FFMPEG_ARGS+=(-c:a:${idx} aac -b:a:${idx} 192k) ;;
        esac
    done

    FFMPEG_ARGS+=(-sn)  # strip subtitles — MP4 can't hold image-based subs

    local num_tracks=${#audio_codecs[@]}
    local all_codecs
    all_codecs=$(IFS='/'; echo "${audio_codecs[*]}")
    CODEC_INFO="$video_codec (${bit_depth}bit) | ${num_tracks} audio track(s) ($all_codecs)"
}

# ── Convert one file ─────────────────────────────────────────
convert_file() {
    local input="$1" output="$2" current="$3" total="$4"

    echo ""
    echo -e "${BOLD}[${current}/${total}]${NC} $(basename "$input")"

    build_ffmpeg_args "$input"

    local input_size
    input_size=$(stat -c%s "$input")
    log INFO "Converting [$current/$total]: $(basename "$input") | $CODEC_INFO | preset=$PRESET"

    mkdir -p "$(dirname "$output")"

    local file_start=$SECONDS
    if ffmpeg -hide_banner -loglevel error -stats \
        -i "$input" \
        "${FFMPEG_ARGS[@]}" \
        -movflags +faststart \
        -map 0:v:0 -map 0:a \
        "$output" 2>&1 \
        | grep --line-buffered -E "^(frame|size|time|speed)" \
        | while IFS= read -r line; do printf "\r  ${CYAN}%-72s${NC}" "$line"; done
    then
        echo ""
        local elapsed=$(( SECONDS - file_start ))
        local output_size
        output_size=$(stat -c%s "$output")
        local saved=$(( input_size - output_size ))

        log INFO "  Done $(format_time $elapsed) | $(format_size $input_size) -> $(format_size $output_size) | saved $(format_size $saved)"
        echo -e "  ${GREEN}Done${NC} in $(format_time $elapsed) | $(format_size $input_size) -> $(format_size $output_size) | saved $(format_size $saved)"

        TOTAL_INPUT_BYTES=$(( TOTAL_INPUT_BYTES + input_size ))
        TOTAL_OUTPUT_BYTES=$(( TOTAL_OUTPUT_BYTES + output_size ))
        TOTAL_FILE_SECS=$(( TOTAL_FILE_SECS + elapsed ))
        (( CONVERTED++ )) || true
    else
        echo ""
        log ERROR "FFmpeg failed for: $input"
        echo -e "  ${RED}Failed${NC} — check $LOG_FILE"
        rm -f "$output"
        (( FAILED++ )) || true
    fi
}

# ── Rolling ETA display ──────────────────────────────────────
show_eta() {
    local current="$1" total="$2"
    local remaining=$(( total - current ))
    (( CONVERTED == 0 || remaining <= 0 )) && return

    local avg_secs=$(( TOTAL_FILE_SECS / CONVERTED ))
    local eta_secs=$(( avg_secs * remaining ))
    local finish
    finish=$(date -d "+${eta_secs} seconds" '+%a %b %d at %I:%M %p' 2>/dev/null || echo "?")

    echo -e "  ${CYAN}ETA: ~$(format_time $eta_secs) remaining (~$(format_time $avg_secs)/file) | est. finish: $finish${NC}"
}

# ════════════════════════════════════════════════════════════
# PLAN MODE
# Scans SOURCE_DIR, groups by series, estimates runtime,
# and generates numbered chunk files targeting ~CHUNK_HOURS hours each.
# Series are never split across chunks.
# ════════════════════════════════════════════════════════════
run_plan_mode() {
    local chunk_dir="$OUTPUT_DIR/chunks"
    mkdir -p "$chunk_dir"

    # Encode rate estimates: seconds per 100MB
    local RATE_COPY RATE_ENCODE
    case "$PRESET" in
        fast)   RATE_COPY=2; RATE_ENCODE=14 ;;
        medium) RATE_COPY=2; RATE_ENCODE=21 ;;
        slow)   RATE_COPY=2; RATE_ENCODE=35 ;;
    esac

    echo "Scanning $SOURCE_DIR for MKV files..."
    mapfile -t ALL_FILES < <(find "$SOURCE_DIR" -type f -iname "*.mkv" | sort)
    local total=${#ALL_FILES[@]}

    if (( total == 0 )); then
        echo -e "${YELLOW}No MKV files found.${NC}"
        exit 0
    fi
    echo -e "Found ${BOLD}${total}${NC} files across $(echo "${ALL_FILES[@]}" | tr ' ' '\n' | sed "s|${SOURCE_DIR}/||" | cut -d/ -f1 | sort -u | wc -l) series.\n"

    # Group files by series
    declare -A SERIES_BYTES
    declare -A SERIES_COUNT
    declare -A SERIES_SAMPLES  # up to 3 sample files per series for probing
    declare -a SERIES_ORDER

    for f in "${ALL_FILES[@]}"; do
        local series
        series=$(get_series "$f")

        if [[ -z "${SERIES_BYTES[$series]+x}" ]]; then
            SERIES_ORDER+=("$series")
            SERIES_BYTES[$series]=0
            SERIES_COUNT[$series]=0
            SERIES_SAMPLES[$series]=""
        fi

        local fsize
        fsize=$(stat -c%s "$f")
        SERIES_BYTES[$series]=$(( SERIES_BYTES[$series] + fsize ))
        SERIES_COUNT[$series]=$(( SERIES_COUNT[$series] + 1 ))

        # Collect up to 3 sample files per series
        local sc
        sc=$(printf '%s' "${SERIES_SAMPLES[$series]}" | grep -c . 2>/dev/null || echo 0)
        if (( sc < 3 )); then
            SERIES_SAMPLES[$series]+="${f}"$'\n'
        fi
    done

    local num_series=${#SERIES_ORDER[@]}
    echo "Probing codec samples across $num_series series (up to 3 files each)..."
    echo "(This takes a minute — grab a coffee)"
    echo ""

    # Estimate time per series
    declare -A SERIES_SECS
    local si=0
    for series in "${SERIES_ORDER[@]}"; do
        (( si++ )) || true
        printf "\r  [%d/%d] Analyzing: %-50s" "$si" "$num_series" "${series:0:50}"

        local copy_count=0 encode_count=0
        while IFS= read -r sf; do
            [[ -z "$sf" ]] && continue
            local vc pf bd=8
            vc=$(ffprobe -v error -select_streams v:0 \
                -show_entries stream=codec_name -of default=nw=1:nk=1 "$sf" 2>/dev/null || echo "unknown")
            pf=$(ffprobe -v error -select_streams v:0 \
                -show_entries stream=pix_fmt -of default=nw=1:nk=1 "$sf" 2>/dev/null || echo "")
            case "$pf" in *10le|*10be|yuv420p10*|yuv444p10*) bd=10 ;; esac
            if [[ "$vc" == "h264" && "$bd" == "8" ]]; then
                (( copy_count++ )) || true
            else
                (( encode_count++ )) || true
            fi
        done <<< "${SERIES_SAMPLES[$series]}"

        local sample_total=$(( copy_count + encode_count ))
        local encode_pct=50
        (( sample_total > 0 )) && encode_pct=$(( encode_count * 100 / sample_total ))

        local total_mb=$(( SERIES_BYTES[$series] / 1048576 ))
        local copy_mb=$(( total_mb * (100 - encode_pct) / 100 ))
        local encode_mb=$(( total_mb * encode_pct / 100 ))
        local est_secs=$(( copy_mb * RATE_COPY / 100 + encode_mb * RATE_ENCODE / 100 ))
        SERIES_SECS[$series]=$est_secs
    done
    printf "\r  Done analyzing %d series.%50s\n\n" "$num_series" ""

    # Greedy bin-packing into ~1-day chunks
    # Series are NEVER split across chunks
    local TARGET_SECS=$(( CHUNK_HOURS * 3600 ))
    local chunk_num=1
    local chunk_secs=0
    declare -a current_chunk=()

    for series in "${SERIES_ORDER[@]}"; do
        local secs=${SERIES_SECS[$series]}

        if (( ${#current_chunk[@]} > 0 && chunk_secs + secs > TARGET_SECS )); then
            # Save current chunk and start a new one
            printf '%s\n' "${current_chunk[@]}" > "$chunk_dir/chunk_$(printf '%03d' $chunk_num).txt"
            (( chunk_num++ )) || true
            current_chunk=("$series")
            chunk_secs=$secs
        else
            current_chunk+=("$series")
            (( chunk_secs += secs )) || true
        fi
    done

    # Save the last chunk
    if (( ${#current_chunk[@]} > 0 )); then
        printf '%s\n' "${current_chunk[@]}" > "$chunk_dir/chunk_$(printf '%03d' $chunk_num).txt"
    fi
    local total_chunks=$chunk_num

    # Print summary
    echo -e "${BOLD}${CYAN}══════════════════ Chunk Plan (~${CHUNK_HOURS}hr targets) ══════════════════${NC}"
    printf "  %-10s %-10s %-10s %s\n" "Chunk" "Series" "Files" "Est. Time"
    echo "  ------------------------------------------------"

    local grand_secs=0
    local grand_files=0
    for (( cn=1; cn<=total_chunks; cn++ )); do
        local cfile="$chunk_dir/chunk_$(printf '%03d' $cn).txt"
        local c_series=0 c_files=0 c_secs=0
        while IFS= read -r s; do
            [[ -z "$s" ]] && continue
            (( c_series++ )) || true
            (( c_files  += SERIES_COUNT[$s] )) || true
            (( c_secs   += SERIES_SECS[$s]  )) || true
        done < "$cfile"
        (( grand_secs  += c_secs  )) || true
        (( grand_files += c_files )) || true
        printf "  %-10s %-10s %-10s %s\n" "Chunk $cn" "$c_series" "$c_files" "~$(format_time $c_secs)"
    done

    echo "  ------------------------------------------------"
    printf "  %-10s %-10s %-10s %s\n" "TOTAL" "$num_series" "$grand_files" "~$(format_time $grand_secs)"
    echo -e "${BOLD}${CYAN}════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  Chunk files saved to: ${BOLD}$chunk_dir${NC}"
    echo ""
    echo -e "${BOLD}To run chunks (recommended: use --preset=fast for TV shows):${NC}"
    for (( cn=1; cn<=total_chunks; cn++ )); do
        echo "  ./convert_mkv_to_mp4.sh --chunk=$cn --preset=fast --hours=$CHUNK_HOURS"
    done
    echo ""
    echo -e "${YELLOW}Note: Time estimates use file-size heuristics. Actual times"
    echo -e "vary based on your CPU and codec mix per series.${NC}"
}

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
print_header
check_deps

# ── Prompt: source folder ────────────────────────────────────
echo -e "${BOLD}Source folder${NC} (where your MKV files are):"
read -rp "  Path: " SOURCE_DIR
SOURCE_DIR="${SOURCE_DIR%/}"

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

# ── Plan mode: generate chunks then exit ─────────────────────
if $PLAN_MODE; then
    log INFO "Plan mode | source=$SOURCE_DIR | preset=$PRESET"
    run_plan_mode
    log INFO "Plan mode complete"
    exit 0
fi

# ── Disk space info ───────────────────────────────────────────
echo ""
AVAIL_BYTES=$(df --output=avail -B1 "$OUTPUT_DIR" | tail -1)
echo -e "${CYAN}Available on output drive:${NC} $(format_size $AVAIL_BYTES)"
echo -e "${YELLOW}Tip:${NC} Re-encodes are typically 30-60% smaller than the source."
echo ""

# ── Confirm ───────────────────────────────────────────────────
echo -e "  Source  : ${BOLD}$SOURCE_DIR${NC}"
echo -e "  Output  : ${BOLD}$OUTPUT_DIR${NC}"
echo -e "  Preset  : ${BOLD}$PRESET${NC}"
(( CHUNK_NUM > 0 )) && echo -e "  Chunk   : ${BOLD}$CHUNK_NUM${NC}"
echo -e "  Log     : ${BOLD}$LOG_FILE${NC}"
echo ""
read -rp "Proceed? [y/N]: " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && echo "Aborted." && exit 0

# ── Find MKV files ───────────────────────────────────────────
echo ""
echo "Scanning for .mkv files..."
mapfile -t MKV_FILES < <(find "$SOURCE_DIR" -type f -iname "*.mkv" | sort)
TOTAL=${#MKV_FILES[@]}

if (( TOTAL == 0 )); then
    echo -e "${YELLOW}No MKV files found.${NC}"
    exit 0
fi

# ── Chunk filtering ──────────────────────────────────────────
if (( CHUNK_NUM > 0 )); then
    CHUNK_FILE="$OUTPUT_DIR/chunks/chunk_$(printf '%03d' $CHUNK_NUM).txt"
    if [[ ! -f "$CHUNK_FILE" ]]; then
        echo -e "${RED}Chunk file not found: $CHUNK_FILE${NC}"
        echo "Run --plan first to generate chunks, then use --chunk=N."
        exit 1
    fi

    mapfile -t CHUNK_SERIES < "$CHUNK_FILE"
    echo "Filtering to chunk $CHUNK_NUM (${#CHUNK_SERIES[@]} series)..."

    FILTERED=()
    for f in "${MKV_FILES[@]}"; do
        local_series=$(get_series "$f")
        for cs in "${CHUNK_SERIES[@]}"; do
            [[ -z "$cs" ]] && continue
            if [[ "$local_series" == "$cs" ]]; then
                FILTERED+=("$f")
                break
            fi
        done
    done

    MKV_FILES=("${FILTERED[@]}")
    TOTAL=${#MKV_FILES[@]}

    if (( TOTAL == 0 )); then
        echo -e "${YELLOW}No files matched chunk $CHUNK_NUM — already done?${NC}"
        exit 0
    fi
fi

echo -e "Processing ${BOLD}${TOTAL}${NC} file(s) | preset: ${BOLD}$PRESET${NC}\n"
log INFO "Starting | files=$TOTAL source=$SOURCE_DIR output=$OUTPUT_DIR preset=$PRESET chunk=$CHUNK_NUM"

# ── Conversion loop ──────────────────────────────────────────
OVERALL_START=$SECONDS

for i in "${!MKV_FILES[@]}"; do
    INPUT="${MKV_FILES[$i]}"
    REL_PATH="${INPUT#${SOURCE_DIR}/}"
    OUTPUT="${OUTPUT_DIR}/${REL_PATH%.mkv}.mp4"
    CURRENT=$(( i + 1 ))

    if [[ -f "$OUTPUT" ]]; then
        log SKIP "Already exists: $(basename "$INPUT")"
        echo -e "${CYAN}[SKIP]${NC}  [${CURRENT}/${TOTAL}] $(basename "$INPUT")"
        (( SKIPPED++ )) || true
        continue
    fi

    convert_file "$INPUT" "$OUTPUT" "$CURRENT" "$TOTAL"
    show_eta "$CURRENT" "$TOTAL"
done

# ── Summary ──────────────────────────────────────────────────
TOTAL_ELAPSED=$(( SECONDS - OVERALL_START ))
echo ""
echo -e "${BOLD}${CYAN}══════════════════ Summary ══════════════════${NC}"
echo -e "  Total files  : $TOTAL"
echo -e "  ${GREEN}Converted    : $CONVERTED${NC}"
echo -e "  ${CYAN}Skipped      : $SKIPPED${NC}"
echo -e "  ${RED}Failed       : $FAILED${NC}"
echo -e "  Preset       : $PRESET"
echo -e "  Total time   : $(format_time $TOTAL_ELAPSED)"
if (( CONVERTED > 0 )); then
    AVG=$(( TOTAL_FILE_SECS / CONVERTED ))
    SAVED=$(( TOTAL_INPUT_BYTES - TOTAL_OUTPUT_BYTES ))
    echo -e "  Avg per file : $(format_time $AVG)"
    echo -e "  Space saved  : $(format_size $SAVED) ($(format_size $TOTAL_INPUT_BYTES) -> $(format_size $TOTAL_OUTPUT_BYTES))"
fi
echo -e "  Log file     : $LOG_FILE"
echo -e "${BOLD}${CYAN}═════════════════════════════════════════════${NC}\n"

log INFO "Done | converted=$CONVERTED skipped=$SKIPPED failed=$FAILED time=$(format_time $TOTAL_ELAPSED) preset=$PRESET chunk=$CHUNK_NUM"
