#!/bin/bash

# ============================================================
# process_shared.sh
# Processes video files dropped into the shared folder from
# a Windows machine. Converts to MP4 (H.264/AAC), then moves
# the converted file to the proper Movies or TV Shows directory
# in the media library.
#
# Expected layout in the shared folder:
#   HYPERION_SHARE/
#   ├── Movies/
#   │   └── Some.Movie.2024.mkv
#   └── TV Shows/
#       ├── Show.Name.S01E01.mkv          (auto-parsed)
#       └── Show Name/                    (preserved)
#           └── Season 01/
#               └── S01E01.Episode.mkv
#
# Usage:
#   ./process_shared.sh                   # Normal run, medium preset
#   ./process_shared.sh --dry-run         # Preview what would happen
#   ./process_shared.sh --preset=fast     # Faster encode
#   ./process_shared.sh --hwaccel         # Auto-detect GPU encoder
#   ./process_shared.sh --crf=23          # Lower quality, faster
#   ./process_shared.sh --keep            # Keep originals after conversion
#
# All flags from convert_mkv_to_mp4.sh are supported:
#   --preset=PRESET   x264 preset (default: medium)
#   --hwaccel[=TYPE]  GPU-accelerated encoding
#   --crf=N           Quality 0-51 (default: 18)
#   --keep            Do not delete originals after successful conversion
#   --dry-run         Preview actions without making changes
# ============================================================

set -euo pipefail

# ── Source config ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_ROOT/config.env" ]]; then
    # shellcheck source=../config.env
    source "$REPO_ROOT/config.env"
fi

SHARE="${HYPERION_SHARE:?Set HYPERION_SHARE in config.env}"
MEDIA="${MEDIA_SOURCE:?Set MEDIA_SOURCE in config.env}"

# ── Parse arguments ──────────────────────────────────────────
PRESET="medium"
HWACCEL=""
CRF=18
DRY_RUN=false
KEEP=false

for arg in "$@"; do
    case $arg in
        --preset=*)
            PRESET="${arg#--preset=}"
            case "$PRESET" in
                ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow) ;;
                *) echo "Invalid preset '$PRESET'."; exit 1 ;;
            esac
            ;;
        --hwaccel)
            HWACCEL="auto"
            ;;
        --hwaccel=*)
            HWACCEL="${arg#--hwaccel=}"
            case "$HWACCEL" in
                auto|vaapi|nvenc|qsv) ;;
                *) echo "Invalid hwaccel '$HWACCEL'."; exit 1 ;;
            esac
            ;;
        --crf=*)
            CRF="${arg#--crf=}"
            if ! [[ "$CRF" =~ ^[0-9]+$ ]] || (( CRF < 0 || CRF > 51 )); then
                echo "Invalid CRF value. Must be 0-51."; exit 1
            fi
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
        --keep)
            KEEP=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--preset=PRESET] [--hwaccel[=TYPE]] [--crf=N] [--keep] [--dry-run]"
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
CONVERTED=0
FAILED=0
SKIPPED=0
TOTAL_INPUT_BYTES=0
TOTAL_OUTPUT_BYTES=0
HWACCEL_DEVICE=""
VAAPI_RENDER_DEVICE=""

# ── Logging ──────────────────────────────────────────────────
LOG_DIR="$SHARE"
LOG_FILE="${LOG_DIR}/process_shared_$(date '+%Y%m%d_%H%M%S').log"

log() {
    local level="$1" msg="$2" timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    if ! $DRY_RUN; then
        echo "[$timestamp] [$level] $msg" >> "$LOG_FILE"
    fi
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
    if   (( secs >= 3600 )); then
        printf "%02dh %02dm %02ds" "$(( secs/3600 ))" "$(( (secs%3600)/60 ))" "$(( secs%60 ))"
    else
        printf "%02dm %02ds" "$(( secs/60 ))" "$(( secs%60 ))"
    fi
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
detect_hwaccel() {
    local requested="${1:-auto}"

    for dev in /dev/dri/renderD*; do
        [[ -e "$dev" ]] && VAAPI_RENDER_DEVICE="$dev" && break
    done

    try_nvenc() {
        nvidia-smi &>/dev/null || return 1
        ffmpeg -hide_banner -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -c:v h264_nvenc -f null - 2>/dev/null
    }
    try_vaapi() {
        [[ -z "$VAAPI_RENDER_DEVICE" ]] && return 1
        ffmpeg -hide_banner -init_hw_device "vaapi=va:${VAAPI_RENDER_DEVICE}" \
            -filter_hw_device va \
            -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -vf 'format=nv12,hwupload' \
            -c:v h264_vaapi -f null - 2>/dev/null
    }
    try_qsv() {
        ffmpeg -hide_banner -init_hw_device qsv=hw \
            -f lavfi -i "nullsrc=s=256x256:d=0.1" \
            -vf 'format=nv12,hwupload=extra_hw_frames=64' \
            -c:v h264_qsv -f null - 2>/dev/null
    }

    case "$requested" in
        auto)
            if try_nvenc; then HWACCEL_DEVICE="nvenc"
            elif try_vaapi; then HWACCEL_DEVICE="vaapi"
            elif try_qsv; then HWACCEL_DEVICE="qsv"
            else
                echo -e "  ${YELLOW}No hardware encoder found — using software.${NC}"
                return
            fi
            ;;
        nvenc)  try_nvenc  && HWACCEL_DEVICE="nvenc"  || { echo -e "${RED}NVENC not available.${NC}"; exit 1; } ;;
        vaapi)  try_vaapi  && HWACCEL_DEVICE="vaapi"  || { echo -e "${RED}VAAPI not available.${NC}"; exit 1; } ;;
        qsv)    try_qsv    && HWACCEL_DEVICE="qsv"    || { echo -e "${RED}QSV not available.${NC}"; exit 1; } ;;
    esac

    echo -e "  ${GREEN}Using hardware encoder: ${BOLD}${HWACCEL_DEVICE}${NC}"
}

# ── Build ffmpeg args for a file ─────────────────────────────
# Sets: FFMPEG_ARGS (array)
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

    if (( height > 720 )); then h264_level="5.1"; else h264_level="4.1"; fi

    # Video encoding strategy
    local needs_encode=false
    case "$video_codec" in
        h264)
            if (( bit_depth == 10 )); then needs_encode=true
            else FFMPEG_ARGS+=(-c:v copy); fi
            ;;
        *) needs_encode=true ;;
    esac

    if $needs_encode; then
        case "$HWACCEL_DEVICE" in
            vaapi)
                FFMPEG_ARGS+=(-init_hw_device "vaapi=va:${VAAPI_RENDER_DEVICE}" -filter_hw_device va)
                FFMPEG_ARGS+=(-c:v h264_vaapi)
                local vaapi_qp=$(( CRF + 2 ))
                FFMPEG_ARGS+=(-qp "$vaapi_qp")
                ;;
            nvenc)
                FFMPEG_ARGS+=(-c:v h264_nvenc -preset p4 -tune hq -rc constqp)
                FFMPEG_ARGS+=(-qp "$CRF" -profile:v high -level "$h264_level")
                ;;
            qsv)
                FFMPEG_ARGS+=(-init_hw_device qsv=hw -filter_hw_device hw)
                FFMPEG_ARGS+=(-c:v h264_qsv)
                local qsv_q=$(( CRF + 2 ))
                FFMPEG_ARGS+=(-global_quality "$qsv_q")
                ;;
            *)
                FFMPEG_ARGS+=(-c:v libx264 -crf "$CRF" -preset "$PRESET" -profile:v high -level "$h264_level")
                ;;
        esac

        if (( bit_depth == 10 )); then
            case "$HWACCEL_DEVICE" in
                vaapi|qsv) ;;
                *) FFMPEG_ARGS+=(-pix_fmt yuv420p) ;;
            esac
        fi
    fi

    # Audio: per-track — copy AAC, re-encode everything else
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
}

# ── Parse TV show info from filename ─────────────────────────
# Extracts show name and season number from filenames like:
#   Show.Name.S01E01.Episode.Title.mkv
#   Show Name - S01E01 - Episode Title.mkv
#   show.name.1x01.episode.mkv
# Sets: PARSED_SHOW, PARSED_SEASON (or empty if no match)
parse_tv_filename() {
    local filename="$1"
    PARSED_SHOW=""
    PARSED_SEASON=""

    # Regex patterns stored in variables (bash requires this for complex patterns)
    local re_sxxexx='^(.+)[. _-]+[Ss]([0-9]{1,2})[Ee][0-9]+'
    local re_nxnn='^(.+)[. _-]+([0-9]{1,2})[xX][0-9]+'

    # Try SxxExx pattern first (most common)
    if [[ "$filename" =~ $re_sxxexx ]]; then
        PARSED_SHOW="${BASH_REMATCH[1]}"
        PARSED_SEASON=$(printf "%d" "${BASH_REMATCH[2]}")
    # Try NxNN pattern
    elif [[ "$filename" =~ $re_nxnn ]]; then
        PARSED_SHOW="${BASH_REMATCH[1]}"
        PARSED_SEASON=$(printf "%d" "${BASH_REMATCH[2]}")
    fi

    if [[ -n "$PARSED_SHOW" ]]; then
        # Clean up show name: replace dots and underscores with spaces, trim
        PARSED_SHOW="${PARSED_SHOW//./ }"
        PARSED_SHOW="${PARSED_SHOW//_/ }"
        PARSED_SHOW="$(echo "$PARSED_SHOW" | sed 's/^ *//;s/ *$//')"
    fi
}

# ── Find matching show directory in media library ────────────
# Looks for an existing directory in TV Shows that matches the
# parsed show name (case-insensitive prefix match).
# Sets: MATCHED_SHOW_DIR (full path) or empty if no match
find_show_dir() {
    local parsed_name="$1"
    local tv_root="$MEDIA/TV Shows"
    MATCHED_SHOW_DIR=""

    local parsed_lower
    parsed_lower=$(echo "$parsed_name" | tr '[:upper:]' '[:lower:]')

    while IFS= read -r -d '' dir; do
        local dirname
        dirname=$(basename "$dir")
        local dirname_lower
        dirname_lower=$(echo "$dirname" | tr '[:upper:]' '[:lower:]')

        # Check if parsed name matches the start of an existing directory
        # e.g. "breaking bad" matches "Breaking Bad (2008) Season 1-5 ..."
        if [[ "$dirname_lower" == "$parsed_lower"* ]] || [[ "$dirname_lower" == *"$parsed_lower"* ]]; then
            MATCHED_SHOW_DIR="$dir"
            return 0
        fi
    done < <(find "$tv_root" -mindepth 1 -maxdepth 1 -type d -print0)

    return 1
}

# ── Convert a single file ────────────────────────────────────
convert_file() {
    local input="$1" output="$2"

    build_ffmpeg_args "$input"

    mkdir -p "$(dirname "$output")"

    # Build the full ffmpeg command
    local ffcmd=(ffmpeg -hide_banner -loglevel error -stats -y)

    # Separate pre-input and post-input args
    local needs_vf=false
    case "$HWACCEL_DEVICE" in
        vaapi)
            printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_vaapi" && needs_vf=true
            ;;
        qsv)
            printf '%s\n' "${FFMPEG_ARGS[@]}" | grep -q "h264_qsv" && needs_vf=true
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
    if "${ffcmd[@]}" 2>&1 \
        | grep --line-buffered -E "^(frame|size|time|speed)" \
        | while IFS= read -r line; do printf "\r  ${CYAN}%-72s${NC}" "$line"; done
    then
        echo ""
        local elapsed=$(( SECONDS - file_start ))
        local input_size output_size saved
        input_size=$(stat -c%s "$input")
        output_size=$(stat -c%s "$output")
        saved=$(( input_size - output_size ))

        log INFO "  Converted in $(format_time $elapsed) | $(format_size $input_size) -> $(format_size $output_size) | saved $(format_size $saved)"

        TOTAL_INPUT_BYTES=$(( TOTAL_INPUT_BYTES + input_size ))
        TOTAL_OUTPUT_BYTES=$(( TOTAL_OUTPUT_BYTES + output_size ))
        (( CONVERTED++ )) || true
        return 0
    else
        echo ""
        log ERROR "FFmpeg failed for: $input"
        rm -f "$output"
        (( FAILED++ )) || true
        return 1
    fi
}

# ── Process a single video file ──────────────────────────────
# Determines the destination path and converts/copies.
process_file() {
    local file="$1" media_type="$2" current="$3" total="$4"
    local basename_file
    basename_file=$(basename "$file")
    local mp4_name="${basename_file%.*}.mp4"

    echo ""
    echo -e "${BOLD}[${current}/${total}]${NC} $basename_file"

    local dest_dir=""

    if [[ "$media_type" == "Movies" ]]; then
        dest_dir="$MEDIA/Movies"
    elif [[ "$media_type" == "TV Shows" ]]; then
        # Determine relative path within the TV Shows share folder
        local tv_share_root="$SHARE/TV Shows"
        local rel="${file#${tv_share_root}/}"
        local parts
        IFS='/' read -ra parts <<< "$rel"

        if (( ${#parts[@]} == 1 )); then
            # Flat file in TV Shows/ — parse show name and season from filename
            parse_tv_filename "$basename_file"

            if [[ -z "$PARSED_SHOW" ]]; then
                log WARN "Cannot parse show/season from: $basename_file — skipping"
                echo -e "  ${YELLOW}Cannot parse show name or season from filename.${NC}"
                echo -e "  ${YELLOW}Place in a 'Show Name/Season XX/' subdirectory, or use SxxExx naming.${NC}"
                (( SKIPPED++ )) || true
                return
            fi

            # Try to match an existing show directory
            if find_show_dir "$PARSED_SHOW"; then
                dest_dir="$MATCHED_SHOW_DIR/Season $(printf '%02d' "$PARSED_SEASON")"
                log INFO "  Matched show: $(basename "$MATCHED_SHOW_DIR") -> Season $PARSED_SEASON"
            else
                # Create a new show directory
                dest_dir="$MEDIA/TV Shows/$PARSED_SHOW/Season $(printf '%02d' "$PARSED_SEASON")"
                log INFO "  New show directory: $PARSED_SHOW -> Season $PARSED_SEASON"
            fi
        else
            # File is in a subdirectory — preserve the structure
            local rel_dir
            rel_dir=$(dirname "$rel")
            dest_dir="$MEDIA/TV Shows/$rel_dir"
        fi
    fi

    local dest_file="$dest_dir/$mp4_name"

    # Check if destination already exists
    if [[ -f "$dest_file" ]]; then
        log SKIP "Already exists in library: $mp4_name"
        (( SKIPPED++ )) || true
        if ! $KEEP && ! $DRY_RUN; then
            rm "$file"
            log INFO "  Removed from share: $basename_file"
        fi
        return
    fi

    local ext="${file##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    if $DRY_RUN; then
        echo -e "  ${GREEN}[CONVERT]${NC} $basename_file"
        echo -e "  ${GREEN}[COPY TO]${NC} $dest_file"
        if ! $KEEP; then
            echo -e "  ${RED}[DELETE]${NC}  $file"
        fi
        (( CONVERTED++ )) || true
        return
    fi

    # Convert to a temp file in the share, then move to destination
    local tmp_output="$SHARE/.converting_${mp4_name}"

    log INFO "Converting: $basename_file -> $mp4_name"
    log INFO "  Destination: $dest_file"

    if convert_file "$file" "$tmp_output"; then
        # Move converted file to destination
        mkdir -p "$dest_dir"
        if mv "$tmp_output" "$dest_file"; then
            log INFO "  Moved to library: $dest_file"

            if ! $KEEP; then
                rm "$file"
                log INFO "  Removed from share: $basename_file"
            fi
        else
            log ERROR "Failed to move to library: $dest_file"
            rm -f "$tmp_output"
            (( CONVERTED-- )) || true
            (( FAILED++ )) || true
        fi
    else
        rm -f "$tmp_output"
    fi
}

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
check_deps

# Validate directories
if [[ ! -d "$SHARE" ]]; then
    echo -e "${RED}Shared folder not found: $SHARE${NC}"
    exit 1
fi
if [[ ! -d "$MEDIA" ]]; then
    echo -e "${RED}Media library not found: $MEDIA${NC}"
    exit 1
fi

# Create intake subdirectories if they don't exist
mkdir -p "$SHARE/Movies" "$SHARE/TV Shows"

# Detect hardware acceleration
if [[ -n "$HWACCEL" ]]; then
    detect_hwaccel "$HWACCEL"
    [[ -z "$HWACCEL_DEVICE" ]] && HWACCEL=""
fi

# Print header
echo ""
echo -e "${BOLD}${CYAN}=========================================${NC}"
echo -e "${BOLD}${CYAN}   Shared Folder Processor${NC}"
echo -e "${BOLD}${CYAN}=========================================${NC}"
echo -e "  Share  : ${BOLD}$SHARE${NC}"
echo -e "  Library: ${BOLD}$MEDIA${NC}"
echo -e "  Preset : ${BOLD}$PRESET${NC}"
echo -e "  CRF    : ${BOLD}$CRF${NC}"
[[ -n "$HWACCEL_DEVICE" ]] && echo -e "  HW Acc : ${BOLD}$HWACCEL_DEVICE${NC}"
$DRY_RUN && echo -e "  Mode   : ${BOLD}${YELLOW}DRY RUN${NC}"
$KEEP && echo -e "  Keep   : ${BOLD}originals preserved${NC}"
echo ""

# Initialize log
if ! $DRY_RUN; then
    touch "$LOG_FILE"
    log INFO "Starting | share=$SHARE media=$MEDIA preset=$PRESET crf=$CRF hwaccel=$HWACCEL_DEVICE"
fi

# ── Collect video files from both subdirectories ─────────────
VIDEO_EXTS=(-iname "*.mkv" -o -iname "*.avi" -o -iname "*.mp4" -o -iname "*.m4v" -o -iname "*.flv" -o -iname "*.wmv" -o -iname "*.mpg")

declare -a FILES=()
declare -a TYPES=()

for media_type in "Movies" "TV Shows"; do
    local_dir="$SHARE/$media_type"
    [[ ! -d "$local_dir" ]] && continue

    while IFS= read -r -d '' f; do
        FILES+=("$f")
        TYPES+=("$media_type")
    done < <(find "$local_dir" -type f \( "${VIDEO_EXTS[@]}" \) -print0 | sort -z)
done

TOTAL=${#FILES[@]}

if (( TOTAL == 0 )); then
    echo -e "${YELLOW}No video files found in $SHARE/Movies/ or $SHARE/TV Shows/${NC}"
    echo ""
    echo -e "Drop video files into these folders from your Windows machine:"
    echo -e "  ${BOLD}$SHARE/Movies/${NC}    — for movies"
    echo -e "  ${BOLD}$SHARE/TV Shows/${NC}  — for TV episodes"
    echo ""
    exit 0
fi

echo -e "Found ${BOLD}${TOTAL}${NC} video file(s) to process."
echo ""

if ! $DRY_RUN; then
    read -rp "Proceed? [y/N]: " CONFIRM
    [[ "${CONFIRM,,}" != "y" ]] && echo "Aborted." && exit 0
fi

# ── Process each file ─────────────────────────────────────────
OVERALL_START=$SECONDS

for i in "${!FILES[@]}"; do
    process_file "${FILES[$i]}" "${TYPES[$i]}" "$(( i + 1 ))" "$TOTAL"
done

# ── Clean up empty directories in the share ───────────────────
if ! $DRY_RUN && ! $KEEP; then
    find "$SHARE/Movies" -type d -empty -delete 2>/dev/null || true
    find "$SHARE/TV Shows" -type d -empty -delete 2>/dev/null || true
    # Re-create the top-level intake dirs in case they were emptied
    mkdir -p "$SHARE/Movies" "$SHARE/TV Shows"
fi

# ── Summary ──────────────────────────────────────────────────
TOTAL_ELAPSED=$(( SECONDS - OVERALL_START ))
echo ""
echo -e "${BOLD}${CYAN}══════════════════ Summary ══════════════════${NC}"
$DRY_RUN && echo -e "  ${YELLOW}(dry run — no changes made)${NC}"
echo -e "  Total files : $TOTAL"
echo -e "  ${GREEN}Converted   : $CONVERTED${NC}"
echo -e "  ${CYAN}Skipped     : $SKIPPED${NC}"
echo -e "  ${RED}Failed      : $FAILED${NC}"
if (( CONVERTED > 0 )) && ! $DRY_RUN; then
    echo -e "  Total time  : $(format_time $TOTAL_ELAPSED)"
    SAVED=$(( TOTAL_INPUT_BYTES - TOTAL_OUTPUT_BYTES ))
    echo -e "  Space saved : $(format_size $SAVED) ($(format_size $TOTAL_INPUT_BYTES) -> $(format_size $TOTAL_OUTPUT_BYTES))"
fi
! $DRY_RUN && echo -e "  Log file    : $LOG_FILE"
echo -e "${BOLD}${CYAN}═════════════════════════════════════════════${NC}"
echo ""

if ! $DRY_RUN; then
    log INFO "Done | converted=$CONVERTED skipped=$SKIPPED failed=$FAILED time=$(format_time $TOTAL_ELAPSED)"
fi
