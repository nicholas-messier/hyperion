#!/bin/bash

# ============================================================
# audit_conversion.sh
# Audits a completed (or in-progress) conversion job by:
#
#   1. Parsing the conversion log for any FAILED files
#   2. Scanning the source directory for non-MKV video files
#      that the conversion script never touches (.avi, .mp4,
#      .divx, .mov, .wmv, .m4v, .mpg, .mpeg, .ts, .vob)
#   3. Scanning for MKV files that have no matching MP4 output
#      (not yet converted or failed)
#   4. Generating a summary report and copy commands
#
# Usage:
#   ./audit_conversion.sh
#
# Output:
#   - Printed report to terminal
#   - audit_report_YYYYMMDD_HHMMSS.txt saved alongside the log
# ============================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Non-MKV video extensions to flag ─────────────────────────
# These are formats the conversion script never touches
OTHER_EXTS=("avi" "divx" "mov" "wmv" "m4v" "mpg" "mpeg" "ts" "vob" "xvid" "mp4")

# ─────────────────────────────────────────────────────────────
print_header() {
    echo -e "\n${BOLD}${CYAN}============================================${NC}"
    echo -e "${BOLD}${CYAN}   Conversion Audit Report${NC}"
    echo -e "${BOLD}${CYAN}============================================${NC}\n"
}

format_size() {
    local bytes=$1
    if   (( bytes >= 1073741824 )); then printf "%.2f GB" "$(echo "scale=2; $bytes/1073741824" | bc)"
    elif (( bytes >= 1048576 ));    then printf "%.2f MB" "$(echo "scale=2; $bytes/1048576"    | bc)"
    else                                 printf "%d KB"   "$(( bytes / 1024 ))"
    fi
}

# ─────────────────────────────────────────────────────────────
print_header

# ── Prompt: log file ──────────────────────────────────────────
echo -e "${BOLD}Conversion log file${NC} (e.g. /mnt/sda1/conversion_20260312_232343.log):"
read -rp "  Path: " LOG_FILE
LOG_FILE="${LOG_FILE%/}"

if [[ ! -f "$LOG_FILE" ]]; then
    echo -e "${RED}Error: Log file not found: $LOG_FILE${NC}"
    exit 1
fi

# ── Prompt: source directory ──────────────────────────────────
echo ""
echo -e "${BOLD}Source directory${NC} (where original MKV/video files are):"
read -rp "  Path: " SOURCE_DIR
SOURCE_DIR="${SOURCE_DIR%/}"

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo -e "${RED}Error: Source directory not found: $SOURCE_DIR${NC}"
    exit 1
fi

# ── Prompt: output directory ─────────────────────────────────
echo ""
echo -e "${BOLD}Output directory${NC} (where converted MP4 files are/were saved):"
read -rp "  Path: " OUTPUT_DIR
OUTPUT_DIR="${OUTPUT_DIR%/}"

if [[ ! -d "$OUTPUT_DIR" ]]; then
    echo -e "${RED}Error: Output directory not found: $OUTPUT_DIR${NC}"
    exit 1
fi

# ── Report output file ────────────────────────────────────────
REPORT_FILE="$(dirname "$LOG_FILE")/audit_report_$(date '+%Y%m%d_%H%M%S').txt"

# ── Helper: write to both terminal and report file ────────────
tee_out() {
    echo -e "$1" | tee -a "$REPORT_FILE"
}

# Initialize report file
echo "Conversion Audit Report" > "$REPORT_FILE"
echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')" >> "$REPORT_FILE"
echo "Log file : $LOG_FILE" >> "$REPORT_FILE"
echo "Source   : $SOURCE_DIR" >> "$REPORT_FILE"
echo "Output   : $OUTPUT_DIR" >> "$REPORT_FILE"
echo "============================================" >> "$REPORT_FILE"

echo ""
echo "Analyzing... please wait."
echo ""

# ════════════════════════════════════════════════════════════
# SECTION 1: FAILED CONVERSIONS FROM LOG
# ════════════════════════════════════════════════════════════
tee_out "\n${BOLD}${RED}[ 1 ] FAILED CONVERSIONS (from log)${NC}"
tee_out "──────────────────────────────────────────────"

mapfile -t FAILED_LINES < <(grep "\[ERROR\] FFmpeg failed for:" "$LOG_FILE" 2>/dev/null || true)

if (( ${#FAILED_LINES[@]} == 0 )); then
    tee_out "${GREEN}  No failed conversions found in log. Great!${NC}"
else
    tee_out "${RED}  Found ${#FAILED_LINES[@]} failed conversion(s):${NC}\n"
    FAILED_TOTAL_BYTES=0
    for line in "${FAILED_LINES[@]}"; do
        # Extract file path from log line
        filepath="${line#*FFmpeg failed for: }"
        filename="$(basename "$filepath")"
        if [[ -f "$filepath" ]]; then
            fsize=$(stat -c%s "$filepath" 2>/dev/null || echo 0)
            FAILED_TOTAL_BYTES=$(( FAILED_TOTAL_BYTES + fsize ))
            tee_out "  ${RED}FAILED${NC}  $(format_size $fsize)  $filename"
        else
            tee_out "  ${RED}FAILED${NC}  (source not found)  $filename"
        fi
    done
    tee_out ""
    tee_out "  Total size of failed files: $(format_size $FAILED_TOTAL_BYTES)"
fi

# ════════════════════════════════════════════════════════════
# SECTION 2: MKV FILES WITH NO MATCHING MP4 OUTPUT
# ════════════════════════════════════════════════════════════
tee_out "\n${BOLD}${YELLOW}[ 2 ] MKV FILES NOT YET CONVERTED (no matching MP4 output)${NC}"
tee_out "──────────────────────────────────────────────"

NOT_CONVERTED=()
NOT_CONVERTED_BYTES=0

while IFS= read -r -d '' mkv_file; do
    rel_path="${mkv_file#${SOURCE_DIR}/}"
    expected_mp4="${OUTPUT_DIR}/${rel_path%.mkv}.mp4"
    if [[ ! -f "$expected_mp4" ]]; then
        NOT_CONVERTED+=("$mkv_file")
        fsize=$(stat -c%s "$mkv_file" 2>/dev/null || echo 0)
        NOT_CONVERTED_BYTES=$(( NOT_CONVERTED_BYTES + fsize ))
    fi
done < <(find "$SOURCE_DIR" -type f -iname "*.mkv" -print0 | sort -z)

if (( ${#NOT_CONVERTED[@]} == 0 )); then
    tee_out "${GREEN}  All MKV files have a corresponding MP4 output. Conversion complete!${NC}"
else
    tee_out "${YELLOW}  Found ${#NOT_CONVERTED[@]} MKV file(s) with no MP4 output:${NC}\n"
    for f in "${NOT_CONVERTED[@]}"; do
        fsize=$(stat -c%s "$f" 2>/dev/null || echo 0)
        tee_out "  ${YELLOW}PENDING${NC}  $(format_size $fsize)  $(basename "$f")"
    done
    tee_out ""
    tee_out "  Total size: $(format_size $NOT_CONVERTED_BYTES)"
fi

# ════════════════════════════════════════════════════════════
# SECTION 3: NON-MKV VIDEO FILES (never touched by script)
# ════════════════════════════════════════════════════════════
tee_out "\n${BOLD}${CYAN}[ 3 ] NON-MKV VIDEO FILES (skipped by conversion script)${NC}"
tee_out "──────────────────────────────────────────────"
tee_out "  Extensions checked: ${OTHER_EXTS[*]}"
tee_out ""

OTHER_FILES=()
OTHER_TOTAL_BYTES=0

# Build find expression for all non-mkv extensions
FIND_ARGS=()
for ext in "${OTHER_EXTS[@]}"; do
    FIND_ARGS+=(-iname "*.${ext}" -o)
done
# Remove trailing -o
unset 'FIND_ARGS[-1]'

while IFS= read -r -d '' other_file; do
    OTHER_FILES+=("$other_file")
    fsize=$(stat -c%s "$other_file" 2>/dev/null || echo 0)
    OTHER_TOTAL_BYTES=$(( OTHER_TOTAL_BYTES + fsize ))
done < <(find "$SOURCE_DIR" -type f \( "${FIND_ARGS[@]}" \) -print0 | sort -z)

if (( ${#OTHER_FILES[@]} == 0 )); then
    tee_out "${GREEN}  No non-MKV video files found.${NC}"
else
    tee_out "${CYAN}  Found ${#OTHER_FILES[@]} non-MKV video file(s):${NC}\n"
    for f in "${OTHER_FILES[@]}"; do
        ext="${f##*.}"
        fsize=$(stat -c%s "$f" 2>/dev/null || echo 0)
        tee_out "  ${CYAN}$(printf '%-7s' "${ext^^}")${NC}  $(format_size $fsize)  $(basename "$f")"
    done
    tee_out ""
    tee_out "  Total size: $(format_size $OTHER_TOTAL_BYTES)"
fi

# ════════════════════════════════════════════════════════════
# SECTION 4: COPY COMMANDS FOR EXTERNAL DRIVE
# ════════════════════════════════════════════════════════════
tee_out "\n${BOLD}[ 4 ] SUGGESTED COPY COMMANDS FOR EXTERNAL DRIVE${NC}"
tee_out "──────────────────────────────────────────────"

EXTERNAL_DRIVE=""
read -rp "  Enter external drive mount point to generate copy commands (or press Enter to skip): " EXTERNAL_DRIVE

if [[ -n "$EXTERNAL_DRIVE" ]]; then
    tee_out ""

    if (( ${#FAILED_LINES[@]} > 0 )); then
        tee_out "  ${RED}# Copy failed MKV files (originals) to external:${NC}"
        for line in "${FAILED_LINES[@]}"; do
            filepath="${line#*FFmpeg failed for: }"
            tee_out "  cp \"$filepath\" \"${EXTERNAL_DRIVE}/\""
        done
        tee_out ""
    fi

    if (( ${#NOT_CONVERTED[@]} > 0 )); then
        tee_out "  ${YELLOW}# Copy unconverted MKV files to external:${NC}"
        for f in "${NOT_CONVERTED[@]}"; do
            tee_out "  cp \"$f\" \"${EXTERNAL_DRIVE}/\""
        done
        tee_out ""
    fi

    if (( ${#OTHER_FILES[@]} > 0 )); then
        tee_out "  ${CYAN}# Copy non-MKV video files to external:${NC}"
        for f in "${OTHER_FILES[@]}"; do
            tee_out "  cp \"$f\" \"${EXTERNAL_DRIVE}/\""
        done
        tee_out ""
    fi

    if (( ${#FAILED_LINES[@]} == 0 && ${#NOT_CONVERTED[@]} == 0 && ${#OTHER_FILES[@]} == 0 )); then
        tee_out "  ${GREEN}Nothing to copy — all files accounted for!${NC}"
    fi
else
    tee_out "  ${YELLOW}Skipped. Re-run script and enter a mount point to generate copy commands.${NC}"
fi

# ════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════
tee_out "\n${BOLD}${CYAN}════════════════ Summary ════════════════${NC}"
tee_out "  Failed conversions    : ${#FAILED_LINES[@]}"
tee_out "  MKV not yet converted : ${#NOT_CONVERTED[@]}"
tee_out "  Non-MKV video files   : ${#OTHER_FILES[@]}"
tee_out "  Report saved to       : $REPORT_FILE"
tee_out "${BOLD}${CYAN}═════════════════════════════════════════${NC}\n"
