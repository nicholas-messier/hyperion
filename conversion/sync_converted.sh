#!/bin/bash
# sync_converted.sh
# Ensure all video files exist as .mp4 in both source and destination.
#
# Phase 1 — Destination -> Source:
#   For each .mp4 in the destination, if the source has the original file
#   with a different extension (mkv, avi, etc.), copy the .mp4 to source
#   and remove the original.
#
# Phase 2 — Source -> Destination:
#   For each .mp4 in the source that is missing from the destination,
#   copy it over (handles shows that were already .mp4 and never converted).
#
# Usage: ./sync_converted.sh [--dry-run]
#
# Options:
#   --dry-run   Show what would be done without making changes

SRC="/data/plex_data"
DST="/media/nmessier/NicksData/sda1"
DIRS=("Movies" "TV Shows")

VIDEO_EXT="mkv|avi|divx|mpg|flv|m4v|wmv"

DRY_RUN=false
[ "$1" = "--dry-run" ] && DRY_RUN=true

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

copied_to_src=0
removed=0
copied_to_dst=0
already_synced=0
errors=0

echo ""
if $DRY_RUN; then
    echo -e "${YELLOW}=== DRY RUN — no changes will be made ===${NC}"
else
    echo -e "${CYAN}=== Syncing converted files ===${NC}"
fi
echo -e "Source:      $SRC"
echo -e "Destination: $DST"
echo ""

# ── Phase 1: Copy converted .mp4 from destination back to source ──
echo -e "${CYAN}══ Phase 1: Destination -> Source (replace originals with converted) ══${NC}"
echo ""

for dir in "${DIRS[@]}"; do
    echo -e "${CYAN}--- $dir ---${NC}"

    while IFS= read -r -d '' dst_file; do
        ext="${dst_file##*.}"
        [ "$ext" != "mp4" ] && continue

        rel_path="${dst_file#$DST/}"
        base_no_ext="${rel_path%.*}"

        src_mp4="$SRC/${rel_path}"
        if [ -f "$src_mp4" ]; then
            ((already_synced++))
            continue
        fi

        # Look for the original source file with a different extension
        original_found=""
        for src_candidate in "$SRC/${base_no_ext}".*; do
            [ -f "$src_candidate" ] || continue
            cand_ext="${src_candidate##*.}"
            cand_ext_lower=$(echo "$cand_ext" | tr '[:upper:]' '[:lower:]')
            if echo "$cand_ext_lower" | grep -qEi "^($VIDEO_EXT)$"; then
                original_found="$src_candidate"
                break
            fi
        done

        if [ -z "$original_found" ]; then
            # No original found — copy converted file to source anyway
            echo -e "  ${GREEN}[COPY -> SRC]${NC} $rel_path  (new to source)"
            ((copied_to_src++))
            if ! $DRY_RUN; then
                mkdir -p "$(dirname "$src_mp4")"
                if ! cp "$dst_file" "$src_mp4"; then
                    echo -e "  ${RED}[ERROR]${NC} Failed to copy: $rel_path"
                    ((copied_to_src--))
                    ((errors++))
                fi
            fi
            continue
        fi

        orig_ext="${original_found##*.}"

        echo -e "  ${GREEN}[COPY -> SRC]${NC} $rel_path"
        echo -e "  ${RED}[DEL]        ${NC} ${original_found#$SRC/}  (.${orig_ext} -> .mp4)"
        ((copied_to_src++))
        ((removed++))
        if ! $DRY_RUN; then
            mkdir -p "$(dirname "$src_mp4")"
            if cp "$dst_file" "$src_mp4"; then
                rm "$original_found"
            else
                echo -e "  ${RED}[ERROR]${NC} Failed to copy: $rel_path"
                ((copied_to_src--))
                ((removed--))
                ((errors++))
            fi
        fi
    done < <(find "$DST/$dir" -type f -print0)
    echo ""
done

# ── Phase 2: Copy source .mp4 files missing from destination ──
echo -e "${CYAN}══ Phase 2: Source -> Destination (copy .mp4 files not yet in dest) ══${NC}"
echo ""

for dir in "${DIRS[@]}"; do
    echo -e "${CYAN}--- $dir ---${NC}"

    while IFS= read -r -d '' src_file; do
        ext="${src_file##*.}"
        [ "$ext" != "mp4" ] && continue

        rel_path="${src_file#$SRC/}"
        dst_mp4="$DST/${rel_path}"

        # Skip if already exists in destination
        [ -f "$dst_mp4" ] && continue

        if $DRY_RUN; then
            echo -e "  ${GREEN}[COPY -> DST]${NC} $rel_path"
            ((copied_to_dst++))
        else
            mkdir -p "$(dirname "$dst_mp4")"
            if cp "$src_file" "$dst_mp4"; then
                echo -e "  ${GREEN}[COPY -> DST]${NC} $rel_path"
                ((copied_to_dst++))
            else
                echo -e "  ${RED}[ERROR]${NC} Failed to copy: $rel_path"
                ((errors++))
            fi
        fi
    done < <(find "$SRC/$dir" -type f -print0)
    echo ""
done

echo -e "${CYAN}=== Summary ===${NC}"
if $DRY_RUN; then
    echo -e "  ${YELLOW}(dry run — no changes made)${NC}"
fi
echo -e "  ${GREEN}Copied to source:      $copied_to_src${NC}  (converted .mp4 replacing originals)"
echo -e "  ${RED}Originals removed:     $removed${NC}"
echo -e "  ${GREEN}Copied to destination: $copied_to_dst${NC}  (source .mp4 not yet in dest)"
echo -e "  Already in sync:      $already_synced"
echo -e "  Errors:               $errors"
