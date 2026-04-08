#!/bin/bash
# verify_conversion.sh
# Verify that all video files from the source plex directory have a
# corresponding converted file in the destination directory.
#
# For each source video file the script looks for:
#   1. An .mp4 with the same base name in the destination (converted)
#   2. The file with its original extension in the destination (copied as-is)
#
# Usage: ./verify_conversion.sh

# Source config.env from repo root for default paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$REPO_ROOT/config.env" ]]; then
    # shellcheck source=../config.env
    source "$REPO_ROOT/config.env"
fi

SRC="${MEDIA_SOURCE:?Set MEDIA_SOURCE in config.env}"
DST="${EXTERNAL_DRIVE_MEDIA:?Set EXTERNAL_DRIVE_MEDIA in config.env}"
if [[ -z "${MEDIA_DIRS+x}" ]]; then
    DIRS=("Movies" "TV Shows")
else
    DIRS=("${MEDIA_DIRS[@]}")
fi

VIDEO_EXT="mkv|mp4|avi|divx|mpg|flv|m4v|wmv"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

matched=0
missing=0
skipped=0
missing_list=()

echo ""
echo -e "${CYAN}=== Conversion Verification ===${NC}"
echo -e "Source:      $SRC"
echo -e "Destination: $DST"
echo -e "Directories: ${DIRS[*]}"
echo ""

for dir in "${DIRS[@]}"; do
    echo -e "${CYAN}--- Checking: $dir ---${NC}"
    dir_matched=0
    dir_missing=0
    dir_skipped=0

    while IFS= read -r -d '' src_file; do
        # Get relative path from source base
        rel_path="${src_file#$SRC/}"
        ext="${src_file##*.}"
        ext_lower=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

        # Skip non-video files
        if ! echo "$ext_lower" | grep -qEi "^($VIDEO_EXT)$"; then
            ((skipped++))
            ((dir_skipped++))
            continue
        fi

        # Build the expected .mp4 path in destination
        base_no_ext="${rel_path%.*}"
        dst_mp4="$DST/${base_no_ext}.mp4"
        dst_same="$DST/${rel_path}"

        if [ -f "$dst_mp4" ]; then
            ((matched++))
            ((dir_matched++))
        elif [ -f "$dst_same" ]; then
            ((matched++))
            ((dir_matched++))
        else
            ((missing++))
            ((dir_missing++))
            missing_list+=("$rel_path")
            echo -e "  ${RED}MISSING:${NC} $rel_path"
        fi
    done < <(find "$SRC/$dir" -type f -print0)

    echo -e "  ${GREEN}Matched: $dir_matched${NC}  |  ${RED}Missing: $dir_missing${NC}  |  Skipped (non-video): $dir_skipped"
    echo ""
done

echo -e "${CYAN}=== Summary ===${NC}"
echo -e "  ${GREEN}Matched:  $matched${NC}"
echo -e "  ${RED}Missing:  $missing${NC}"
echo -e "  Skipped:  $skipped (non-video files)"
echo ""

if [ "$missing" -eq 0 ]; then
    echo -e "${GREEN}All video files accounted for in destination.${NC}"
else
    echo -e "${YELLOW}Missing files:${NC}"
    for f in "${missing_list[@]}"; do
        echo "  $f"
    done
fi
