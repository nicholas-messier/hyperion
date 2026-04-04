#!/bin/bash

# ============================================================
# convert_mkv_to_mp4.sh
# Converts MKV files to MP4 (H.264/AAC) for Plex/ErsatzTV
# direct play compatibility on iPhone and other devices.
#
# Usage:
#   ./convert_mkv_to_mp4.sh                        # Normal run, medium preset
#   ./convert_mkv_to_mp4.sh --preset=fast          # Faster encode
#   ./convert_mkv_to_mp4.sh --preset=ultrafast     # Fastest software encode
#   ./convert_mkv_to_mp4.sh --preset=slow          # Smallest files
#   ./convert_mkv_to_mp4.sh --hwaccel              # Auto-detect GPU encoder
#   ./convert_mkv_to_mp4.sh --hwaccel=vaapi        # Force VAAPI (Intel)
#   ./convert_mkv_to_mp4.sh --hwaccel=nvenc        # Force NVENC (NVIDIA)
#   ./convert_mkv_to_mp4.sh --parallel=4           # Process 4 files at once
#   ./convert_mkv_to_mp4.sh --crf=23               # Lower quality, faster encode
#   ./convert_mkv_to_mp4.sh --plan                 # Generate ~12hr chunk files (default)
#   ./convert_mkv_to_mp4.sh --plan --hours=8       # Generate ~8hr chunk files
#   ./convert_mkv_to_mp4.sh --chunk=1              # Run only chunk 1
#   ./convert_mkv_to_mp4.sh --chunk=2 --preset=fast
#
# Speed options (combine for maximum throughput):
#   --preset=ultrafast   Fastest x264 preset (big files, ~4x faster than medium)
#   --hwaccel[=TYPE]     GPU-accelerated encoding (3-10x faster than software)
#   --parallel=N         Convert N files simultaneously (great with many cores)
#   --crf=N              Quality 0-51 (default 18; 23 is faster, still good quality)
#
# Features:
#   - Stream copies video/audio if already compatible (very fast)
#   - Re-encodes only what needs to change
#   - Handles 10-bit HEVC/H.265 correctly
#   - Preserves ALL audio tracks (all languages, commentary, etc.)
#   - Preserves folder structure in output directory
#   - Skips already-converted files (safe to resume)
#   - Rolling ETA updated after every file
#   - Hardware-accelerated encoding (VAAPI/NVENC/QSV auto-detection)
#   - Parallel file processing for multi-core systems
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
HWACCEL=""
PARALLEL=1
CRF=18

for arg in "$@"; do
    case $arg in
        --preset=*)
            PRESET="${arg#--preset=}"
            case "$PRESET" in
                ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow) ;;
                *) echo "Invalid preset '$PRESET'. Use: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, or veryslow."; exit 1 ;;
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
        --hwaccel)
            HWACCEL="auto"
            ;;
        --hwaccel=*)
            HWACCEL="${arg#--hwaccel=}"
            case "$HWACCEL" in
                auto|vaapi|nvenc|qsv) ;;
                *) echo "Invalid hwaccel '$HWACCEL'. Use: auto, vaapi, nvenc, or qsv."; exit 1 ;;
            esac
            ;;
        --parallel=*)
            PARALLEL="${arg#--parallel=}"
            if ! [[ "$PARALLEL" =~ ^[0-9]+$ ]] || (( PARALLEL < 1 )); then
                echo "Invalid parallel value. Must be a positive integer."
                exit 1
            fi
            ;;
        --crf=*)
            CRF="${arg#--crf=}"
            if ! [[ "$CRF" =~ ^[0-9]+$ ]] || (( CRF < 0 || CRF > 51 )); then
                echo "Invalid CRF value. Must be 0-51 (lower = better quality, slower)."
                exit 1
            fi
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--preset=PRESET] [--hwaccel[=TYPE]] [--parallel=N] [--crf=N] [--plan] [--hours=N] [--chunk=N]"
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
HWACCEL_DEVICE=""       # resolved: vaapi, nvenc, qsv, or empty
VAAPI_RENDER_DEVICE=""  # e.g. /dev/dri/renderD128

# ── Print header ─────────────────────────────────────────────
print_header() {
    echo -e "\n${BOLD}${CYAN}=========================================${NC}"
    echo -e "${BOLD}${CYAN}   MKV -> MP4 Converter for Plex/ErsatzTV${NC}"
    echo -e "${BOLD}${CYAN}=========================================${NC}"
    echo -e "  Preset : ${BOLD}$PRESET${NC}"
    echo -e "  CRF    : ${BOLD}$CRF${NC}"
    if [[ -n "$HWACCEL_DEVICE" ]]; then
        echo -e "  HW Acc : ${BOLD}$HWACCEL_DEVICE${NC}"
    elif [[ -n "$HWACCEL" ]]; then
        echo -e "  HW Acc : ${BOLD}detecting...${NC}"
    fi
    if (( PARALLEL > 1 )); then
        echo -e "  Parallel: ${BOLD}${PARALLEL} jobs${NC}"
    fi
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

# ── Detect hardware acceleration ─────────────────────────────
# Probes the system for available GPU encoders.
# Sets HWACCEL_DEVICE to vaapi/nvenc/qsv or empty on failure.
detect_hwaccel() {
    local requested="${1:-auto}"

    echo -e "  Detecting hardware encoders..."

    # Find VAAPI render device
    for dev in /dev/dri/renderD*; do
        [[ -e "$dev" ]] && VAAPI_RENDER_DEVICE="$dev" && break
    done

    try_nvenc() {
        nvidia-smi &>/dev/null || return 1
        ffmpeg -hide_banner -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -c:v h264_nvenc -f null - 2>/dev/null
    }

    try_qsv() {
        ffmpeg -hide_banner -init_hw_device qsv=hw \
            -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -vf 'format=nv12,hwupload=extra_hw_frames=64' \
            -c:v h264_qsv -f null - 2>/dev/null
    }

    try_vaapi() {
        [[ -z "$VAAPI_RENDER_DEVICE" ]] && return 1
        ffmpeg -hide_banner -init_hw_device "vaapi=va:${VAAPI_RENDER_DEVICE}" \
            -filter_hw_device va \
            -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -vf 'format=nv12,hwupload' \
            -c:v h264_vaapi -f null - 2>/dev/null
    }

    case "$requested" in
        auto)
            if try_nvenc; then
                HWACCEL_DEVICE="nvenc"
            elif try_vaapi; then
                HWACCEL_DEVICE="vaapi"
            elif try_qsv; then
                HWACCEL_DEVICE="qsv"
            else
                echo -e "  ${YELLOW}No working hardware encoder found — falling back to software.${NC}"
                HWACCEL_DEVICE=""
                return
            fi
            ;;
        nvenc)
            if try_nvenc; then HWACCEL_DEVICE="nvenc"
            else echo -e "${RED}NVENC not available (no NVIDIA GPU or driver).${NC}"; exit 1; fi
            ;;
        vaapi)
            if try_vaapi; then HWACCEL_DEVICE="vaapi"
            else echo -e "${RED}VAAPI not available (no render device at ${VAAPI_RENDER_DEVICE:-/dev/dri/renderD*}).${NC}"; exit 1; fi
            ;;
        qsv)
            if try_qsv; then HWACCEL_DEVICE="qsv"
            else echo -e "${RED}QSV not available.${NC}"; exit 1; fi
            ;;
    esac

    echo -e "  ${GREEN}Using hardware encoder: ${BOLD}${HWACCEL_DEVICE}${NC}"
}

# ── Build ffmpeg args for a file ─────────────────────────────
# Sets globals: FFMPEG_ARGS (array), CODEC_INFO (string)
build_ffmpeg_args() {
    local input="$1"
    FFMPEG_ARGS=()

    local video_codec pix_fmt bit_depth height h264_level
    video_codec=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=codec_name -of default=nw=1:nk=1 "$input" 2>/dev/null)
    pix_fmt=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=pix_fmt -of default=nw=1:nk=1 "$input" 2>/dev/null)
    height=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=height -of default=nw=1:nk=1 "$input" 2>/dev/null)
    height=${height:-0}

    case "$pix_fmt" in
        *10le|*10be|yuv420p10*|yuv444p10*) bit_depth=10 ;;
        *) bit_depth=8 ;;
    esac

    # H.264 Level 4.1 caps out at 720p bitrates; use 5.1 for 1080p+
    if (( height > 720 )); then
        h264_level="5.1"
    else
        h264_level="4.1"
    fi

    # Video encoding strategy
    local needs_encode=false
    case "$video_codec" in
        h264)
            if (( bit_depth == 10 )); then
                needs_encode=true
            else
                FFMPEG_ARGS+=(-c:v copy)
            fi
            ;;
        *)
            needs_encode=true
            ;;
    esac

    if $needs_encode; then
        case "$HWACCEL_DEVICE" in
            vaapi)
                # VAAPI hardware encoding — prepend HW init args
                FFMPEG_ARGS+=(-init_hw_device "vaapi=va:${VAAPI_RENDER_DEVICE}" -filter_hw_device va)
                # -vf is added in convert_file via -filter_complex / input overrides
                # We store a marker so convert_file knows to add the video filter
                FFMPEG_ARGS+=(-c:v h264_vaapi)
                # VAAPI quality: -qp maps roughly to CRF (lower = better)
                # CRF 18 ≈ qp 20, CRF 23 ≈ qp 25
                local vaapi_qp=$(( CRF + 2 ))
                FFMPEG_ARGS+=(-qp "$vaapi_qp")
                ;;
            nvenc)
                FFMPEG_ARGS+=(-c:v h264_nvenc -preset p4 -tune hq -rc constqp)
                # NVENC quality: -cq maps to CRF (similar scale)
                FFMPEG_ARGS+=(-qp "$CRF")
                FFMPEG_ARGS+=(-profile:v high -level "$h264_level")
                ;;
            qsv)
                FFMPEG_ARGS+=(-init_hw_device qsv=hw -filter_hw_device hw)
                FFMPEG_ARGS+=(-c:v h264_qsv)
                local qsv_q=$(( CRF + 2 ))
                FFMPEG_ARGS+=(-global_quality "$qsv_q")
                ;;
            *)
                # Software encoding with libx264
                FFMPEG_ARGS+=(-c:v libx264 -crf "$CRF" -preset "$PRESET" -profile:v high -level "$h264_level")
                ;;
        esac

        # Pixel format: force 8-bit output for 10-bit sources (software & non-VAAPI HW)
        if (( bit_depth == 10 )); then
            case "$HWACCEL_DEVICE" in
                vaapi|qsv) ;; # handled by hwupload filter
                *)         FFMPEG_ARGS+=(-pix_fmt yuv420p) ;;
            esac
        fi
    fi

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
    local enc_label="$PRESET"
    [[ -n "$HWACCEL_DEVICE" ]] && $needs_encode && enc_label="$HWACCEL_DEVICE"
    CODEC_INFO="$video_codec (${bit_depth}bit) | ${num_tracks} audio track(s) ($all_codecs) | enc=$enc_label"
}

# ── Convert one file ─────────────────────────────────────────
convert_file() {
    local input="$1" output="$2" current="$3" total="$4"

    echo ""
    echo -e "${BOLD}[${current}/${total}]${NC} $(basename "$input")"

    build_ffmpeg_args "$input"

    local input_size
    input_size=$(stat -c%s "$input")
    log INFO "Converting [$current/$total]: $(basename "$input") | $CODEC_INFO | crf=$CRF"

    mkdir -p "$(dirname "$output")"

    # Build the full ffmpeg command
    local ffcmd=(ffmpeg -hide_banner -loglevel error -stats)

    # For VAAPI/QSV, we need special input handling for the hw upload filter
    local needs_vf=false
    case "$HWACCEL_DEVICE" in
        vaapi)
            # Check if we're actually encoding (not just copying)
            if printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_vaapi"; then
                needs_vf=true
            fi
            ;;
        qsv)
            if printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_qsv"; then
                needs_vf=true
            fi
            ;;
    esac

    # Extract init_hw_device args and put them before -i
    local pre_input_args=()
    local post_input_args=()
    local skip_next=false
    for (( ai=0; ai<${#FFMPEG_ARGS[@]}; ai++ )); do
        if $skip_next; then skip_next=false; continue; fi
        case "${FFMPEG_ARGS[$ai]}" in
            -init_hw_device|-filter_hw_device)
                pre_input_args+=("${FFMPEG_ARGS[$ai]}" "${FFMPEG_ARGS[$((ai+1))]}")
                skip_next=true
                ;;
            *)
                post_input_args+=("${FFMPEG_ARGS[$ai]}")
                ;;
        esac
    done

    ffcmd+=("${pre_input_args[@]}")
    ffcmd+=(-i "$input")

    # Add video filter for hw upload if needed
    if $needs_vf; then
        case "$HWACCEL_DEVICE" in
            vaapi) ffcmd+=(-vf 'format=nv12,hwupload') ;;
            qsv)   ffcmd+=(-vf 'format=nv12,hwupload=extra_hw_frames=64') ;;
        esac
    fi

    ffcmd+=("${post_input_args[@]}")
    ffcmd+=(-movflags +faststart -map 0:v:0 -map 0:a "$output")

    local file_start=$SECONDS
    if "${ffcmd[@]}" 2>&1 \
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

# ── Convert one file (parallel worker) ───────────────────────
# Runs in a subshell; writes results to a temp file instead of
# modifying shared globals.
convert_file_parallel() {
    local input="$1" output="$2" current="$3" total="$4" result_file="$5"

    build_ffmpeg_args "$input"

    local input_size
    input_size=$(stat -c%s "$input")
    log INFO "Converting [$current/$total]: $(basename "$input") | $CODEC_INFO | crf=$CRF"

    mkdir -p "$(dirname "$output")"

    # Build ffmpeg command (same logic as convert_file)
    local ffcmd=(ffmpeg -hide_banner -loglevel error -stats)

    local needs_vf=false
    case "$HWACCEL_DEVICE" in
        vaapi)
            if printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_vaapi"; then
                needs_vf=true
            fi
            ;;
        qsv)
            if printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_qsv"; then
                needs_vf=true
            fi
            ;;
    esac

    local pre_input_args=()
    local post_input_args=()
    local skip_next=false
    for (( ai=0; ai<${#FFMPEG_ARGS[@]}; ai++ )); do
        if $skip_next; then skip_next=false; continue; fi
        case "${FFMPEG_ARGS[$ai]}" in
            -init_hw_device|-filter_hw_device)
                pre_input_args+=("${FFMPEG_ARGS[$ai]}" "${FFMPEG_ARGS[$((ai+1))]}")
                skip_next=true
                ;;
            *)
                post_input_args+=("${FFMPEG_ARGS[$ai]}")
                ;;
        esac
    done

    ffcmd+=("${pre_input_args[@]}")
    ffcmd+=(-i "$input")

    if $needs_vf; then
        case "$HWACCEL_DEVICE" in
            vaapi) ffcmd+=(-vf 'format=nv12,hwupload') ;;
            qsv)   ffcmd+=(-vf 'format=nv12,hwupload=extra_hw_frames=64') ;;
        esac
    fi

    ffcmd+=("${post_input_args[@]}")
    ffcmd+=(-movflags +faststart -map 0:v:0 -map 0:a "$output")

    local file_start=$SECONDS
    local err_file="${result_file%.txt}.err"
    if "${ffcmd[@]}" 2>"$err_file"; then
        local elapsed=$(( SECONDS - file_start ))
        local output_size
        output_size=$(stat -c%s "$output")
        local saved=$(( input_size - output_size ))
        echo "OK $input_size $output_size $elapsed" > "$result_file"
        log INFO "  Done $(format_time $elapsed) | $(format_size $input_size) -> $(format_size $output_size) | saved $(format_size $saved)"
        echo -e "  ${GREEN}[${current}/${total}]${NC} $(basename "$input") — done in $(format_time $elapsed)"
        rm -f "$err_file"
    else
        echo "FAIL 0 0 0" > "$result_file"
        log ERROR "FFmpeg failed for: $input"
        if [[ -s "$err_file" ]]; then
            log ERROR "  $(tail -5 "$err_file" | tr '\n' ' ')"
        fi
        echo -e "  ${RED}[${current}/${total}]${NC} $(basename "$input") — FAILED"
        rm -f "$output" "$err_file"
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
    # HW accel and parallel adjustments applied below
    local RATE_COPY RATE_ENCODE
    case "$PRESET" in
        ultrafast)  RATE_COPY=2; RATE_ENCODE=6  ;;
        superfast)  RATE_COPY=2; RATE_ENCODE=8  ;;
        veryfast)   RATE_COPY=2; RATE_ENCODE=10 ;;
        faster)     RATE_COPY=2; RATE_ENCODE=12 ;;
        fast)       RATE_COPY=2; RATE_ENCODE=14 ;;
        medium)     RATE_COPY=2; RATE_ENCODE=21 ;;
        slow)       RATE_COPY=2; RATE_ENCODE=35 ;;
        slower)     RATE_COPY=2; RATE_ENCODE=50 ;;
        veryslow)   RATE_COPY=2; RATE_ENCODE=70 ;;
    esac

    # Hardware acceleration makes encoding ~4-8x faster
    if [[ -n "$HWACCEL_DEVICE" ]]; then
        case "$HWACCEL_DEVICE" in
            nvenc) RATE_ENCODE=$(( RATE_ENCODE / 8 )); (( RATE_ENCODE < 1 )) && RATE_ENCODE=1 ;;
            vaapi) RATE_ENCODE=$(( RATE_ENCODE / 5 )); (( RATE_ENCODE < 1 )) && RATE_ENCODE=1 ;;
            qsv)   RATE_ENCODE=$(( RATE_ENCODE / 5 )); (( RATE_ENCODE < 1 )) && RATE_ENCODE=1 ;;
        esac
    fi

    # Parallel processing reduces wall-clock time
    if (( PARALLEL > 1 )); then
        RATE_COPY=$(( RATE_COPY / PARALLEL ))
        RATE_ENCODE=$(( RATE_ENCODE / PARALLEL ))
        (( RATE_COPY < 1 )) && RATE_COPY=1
        (( RATE_ENCODE < 1 )) && RATE_ENCODE=1
    fi

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

    # Build recommended command based on current flags
    local rec_flags="--preset=$PRESET"
    [[ -n "$HWACCEL_DEVICE" ]] && rec_flags+=" --hwaccel=$HWACCEL_DEVICE"
    (( PARALLEL > 1 )) && rec_flags+=" --parallel=$PARALLEL"
    (( CRF != 18 )) && rec_flags+=" --crf=$CRF"

    echo -e "${BOLD}To run chunks:${NC}"
    for (( cn=1; cn<=total_chunks; cn++ )); do
        echo "  ./convert_mkv_to_mp4.sh --chunk=$cn $rec_flags --hours=$CHUNK_HOURS"
    done
    echo ""
    echo -e "${BOLD}Fastest possible (GPU + parallel):${NC}"
    if [[ -n "$HWACCEL_DEVICE" ]]; then
        echo "  ./convert_mkv_to_mp4.sh --chunk=1 --hwaccel=$HWACCEL_DEVICE --parallel=4 --crf=23 --hours=$CHUNK_HOURS"
    else
        echo "  ./convert_mkv_to_mp4.sh --chunk=1 --preset=ultrafast --parallel=4 --crf=23 --hours=$CHUNK_HOURS"
    fi
    echo ""
    echo -e "${YELLOW}Note: Time estimates use file-size heuristics. Actual times"
    echo -e "vary based on your CPU/GPU and codec mix per series.${NC}"
}

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
check_deps

# ── Detect hardware acceleration (before header) ─────────────
if [[ -n "$HWACCEL" ]]; then
    detect_hwaccel "$HWACCEL"
    # Clear request flag if no device was found (so header doesn't show "detecting...")
    [[ -z "$HWACCEL_DEVICE" ]] && HWACCEL=""
fi

print_header

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
    log INFO "Plan mode | source=$SOURCE_DIR | preset=$PRESET | hwaccel=$HWACCEL_DEVICE | parallel=$PARALLEL | crf=$CRF"
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
echo -e "  Source   : ${BOLD}$SOURCE_DIR${NC}"
echo -e "  Output   : ${BOLD}$OUTPUT_DIR${NC}"
echo -e "  Preset   : ${BOLD}$PRESET${NC}"
echo -e "  CRF      : ${BOLD}$CRF${NC}"
[[ -n "$HWACCEL_DEVICE" ]] && echo -e "  HW Accel : ${BOLD}$HWACCEL_DEVICE${NC}"
(( PARALLEL > 1 )) && echo -e "  Parallel : ${BOLD}${PARALLEL} jobs${NC}"
(( CHUNK_NUM > 0 )) && echo -e "  Chunk    : ${BOLD}$CHUNK_NUM${NC}"
echo -e "  Log      : ${BOLD}$LOG_FILE${NC}"
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

echo -e "Processing ${BOLD}${TOTAL}${NC} file(s) | preset: ${BOLD}$PRESET${NC} | crf: ${BOLD}$CRF${NC}"
[[ -n "$HWACCEL_DEVICE" ]] && echo -e "  Hardware encoder: ${BOLD}$HWACCEL_DEVICE${NC}"
(( PARALLEL > 1 )) && echo -e "  Parallel jobs: ${BOLD}$PARALLEL${NC}"
echo ""
log INFO "Starting | files=$TOTAL source=$SOURCE_DIR output=$OUTPUT_DIR preset=$PRESET crf=$CRF hwaccel=$HWACCEL_DEVICE parallel=$PARALLEL chunk=$CHUNK_NUM"

# ── Conversion loop ──────────────────────────────────────────
OVERALL_START=$SECONDS

if (( PARALLEL > 1 )); then
    # ── Parallel conversion mode ─────────────────────────────
    RESULT_DIR=$(mktemp -d)
    trap "rm -rf '$RESULT_DIR'" EXIT

    active_jobs=0
    for i in "${!MKV_FILES[@]}"; do
        INPUT="${MKV_FILES[$i]}"
        REL_PATH="${INPUT#${SOURCE_DIR}/}"
        OUTPUT="${OUTPUT_DIR}/${REL_PATH%.mkv}.mp4"
        CURRENT=$(( i + 1 ))

        if [[ -f "$OUTPUT" ]]; then
            echo "SKIP 0 0 0" > "$RESULT_DIR/result_${CURRENT}.txt"
            log SKIP "Already exists: $(basename "$INPUT")"
            echo -e "${CYAN}[SKIP]${NC}  [${CURRENT}/${TOTAL}] $(basename "$INPUT")"
            continue
        fi

        (
            convert_file_parallel "$INPUT" "$OUTPUT" "$CURRENT" "$TOTAL" "$RESULT_DIR/result_${CURRENT}.txt"
        ) &

        (( active_jobs++ )) || true
        if (( active_jobs >= PARALLEL )); then
            wait -n 2>/dev/null || true
            (( active_jobs-- )) || true
        fi
    done
    wait

    # Aggregate results from temp files
    for rf in "$RESULT_DIR"/result_*.txt; do
        [[ -f "$rf" ]] || continue
        read -r status in_sz out_sz elapsed < "$rf"
        case "$status" in
            OK)
                (( CONVERTED++ )) || true
                TOTAL_INPUT_BYTES=$(( TOTAL_INPUT_BYTES + in_sz ))
                TOTAL_OUTPUT_BYTES=$(( TOTAL_OUTPUT_BYTES + out_sz ))
                TOTAL_FILE_SECS=$(( TOTAL_FILE_SECS + elapsed ))
                ;;
            SKIP)
                (( SKIPPED++ )) || true
                ;;
            FAIL)
                (( FAILED++ )) || true
                ;;
        esac
    done
    rm -rf "$RESULT_DIR"
else
    # ── Sequential conversion mode (original) ────────────────
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
fi

# ── Summary ──────────────────────────────────────────────────
TOTAL_ELAPSED=$(( SECONDS - OVERALL_START ))
echo ""
echo -e "${BOLD}${CYAN}══════════════════ Summary ══════════════════${NC}"
echo -e "  Total files  : $TOTAL"
echo -e "  ${GREEN}Converted    : $CONVERTED${NC}"
echo -e "  ${CYAN}Skipped      : $SKIPPED${NC}"
echo -e "  ${RED}Failed       : $FAILED${NC}"
echo -e "  Preset       : $PRESET"
echo -e "  CRF          : $CRF"
[[ -n "$HWACCEL_DEVICE" ]] && echo -e "  HW Accel     : $HWACCEL_DEVICE"
(( PARALLEL > 1 )) && echo -e "  Parallel     : $PARALLEL jobs"
echo -e "  Total time   : $(format_time $TOTAL_ELAPSED)"
if (( CONVERTED > 0 )); then
    AVG=$(( TOTAL_FILE_SECS / CONVERTED ))
    SAVED=$(( TOTAL_INPUT_BYTES - TOTAL_OUTPUT_BYTES ))
    echo -e "  Avg per file : $(format_time $AVG)"
    echo -e "  Space saved  : $(format_size $SAVED) ($(format_size $TOTAL_INPUT_BYTES) -> $(format_size $TOTAL_OUTPUT_BYTES))"
fi
echo -e "  Log file     : $LOG_FILE"
echo -e "${BOLD}${CYAN}═════════════════════════════════════════════${NC}\n"

log INFO "Done | converted=$CONVERTED skipped=$SKIPPED failed=$FAILED time=$(format_time $TOTAL_ELAPSED) preset=$PRESET crf=$CRF hwaccel=$HWACCEL_DEVICE parallel=$PARALLEL chunk=$CHUNK_NUM"
