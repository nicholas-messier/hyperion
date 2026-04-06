# Video Conversion Tools

Batch video conversion pipeline for the Hyperion Plex/ErsatzTV library. Converts non-MP4 video files
to H.264/AAC `.mp4` for direct play compatibility on iPhone and other devices, then syncs and verifies
between source and destination drives.

---

## Scripts

### `convert_mkv_to_mp4.sh`

Batch converts video files (MKV, AVI, MP4, M4V, FLV, WMV) to MP4 (H.264/AAC).

**Features:**
- Stream copies video/audio if already compatible (very fast)
- Re-encodes only what needs to change
- Handles 10-bit HEVC/H.265 correctly
- Preserves ALL audio tracks (all languages, commentary, etc.)
- Preserves folder structure in output directory
- Skips already-converted files (safe to resume)
- Rolling ETA updated after every file
- Hardware-accelerated encoding (VAAPI/NVENC/QSV auto-detection)
- Parallel file processing for multi-core systems
- Chunk planner splits large libraries into ~1-day runs without ever breaking a series mid-way through
- Full log written to output directory

**Usage:**
```bash
# Basic run — prompts for source and output folders (medium preset)
./convert_mkv_to_mp4.sh

# Faster preset — recommended for large TV show libraries
./convert_mkv_to_mp4.sh --preset=fast

# Fastest software encode — biggest files, maximum speed
./convert_mkv_to_mp4.sh --preset=ultrafast

# Hardware-accelerated encoding (auto-detects VAAPI/NVENC/QSV)
./convert_mkv_to_mp4.sh --hwaccel

# Force a specific GPU encoder
./convert_mkv_to_mp4.sh --hwaccel=vaapi    # Intel GPU
./convert_mkv_to_mp4.sh --hwaccel=nvenc    # NVIDIA GPU

# Convert 4 files simultaneously
./convert_mkv_to_mp4.sh --parallel=4

# Relax quality for faster encoding (default CRF is 18, x264 default is 23)
./convert_mkv_to_mp4.sh --crf=23

# Maximum speed — combine all options
./convert_mkv_to_mp4.sh --hwaccel --parallel=4 --crf=23

# Generate a chunk plan targeting ~12hr jobs (default)
./convert_mkv_to_mp4.sh --plan --preset=fast

# Generate a chunk plan targeting ~8hr jobs
./convert_mkv_to_mp4.sh --plan --hours=8 --preset=fast

# Run a specific chunk
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
./convert_mkv_to_mp4.sh --chunk=2 --hwaccel --parallel=3 --crf=23
```

**Speed options:**

| Flag | Effect | Speed Gain |
|------|--------|------------|
| `--hwaccel[=TYPE]` | GPU-accelerated encoding (auto, vaapi, nvenc, qsv) | ~3-10x faster |
| `--parallel=N` | Convert N files at the same time | ~Nx throughput |
| `--preset=ultrafast` | Fastest x264 software preset (larger files) | ~4x vs medium |
| `--crf=N` | Quality 0-51, higher = faster/smaller (default 18) | ~1.5-2x at CRF 23 |

> **Note:** `--preset` only affects software encoding. When using `--hwaccel`, the GPU encoder handles its own speed/quality tradeoffs via `--crf`.

**Preset options:** `ultrafast` | `superfast` | `veryfast` | `faster` | `fast` | `medium` (default) | `slow` | `slower` | `veryslow`

**What gets re-encoded vs stream copied:**

| Video Codec | Bit Depth | Action |
|-------------|-----------|--------|
| H.264 | 8-bit | Stream copy (very fast) |
| H.264 | 10-bit | Re-encode (10-bit not compatible with most devices) |
| HEVC/x265 | Any | Re-encode |
| AV1, VC-1, etc. | Any | Re-encode |

| Audio Codec | Action |
|-------------|--------|
| AAC | Stream copy |
| DTS, TrueHD, AC3, EAC3, etc. | Re-encode to AAC 192k |

---

### `sync_converted.sh`

Two-phase bidirectional sync between source and destination drives.

**Phase 1 (Destination -> Source):** For each converted `.mp4` on the destination, copies it back to source and removes the original non-MP4 file (e.g., `.mkv` replaced by `.mp4`).

**Phase 2 (Source -> Destination):** Copies any `.mp4` files in source that are missing from the destination.

**Usage:**
```bash
# Preview what would happen
./sync_converted.sh --dry-run

# Run the sync
./sync_converted.sh

# Long-running — use tmux
tmux new-session -d -s sync 'bash sync_converted.sh 2>&1 | tee /tmp/sync_output.log'
```

**Configuration** (edit variables at top of script):
```bash
SRC="/data/plex_data"
DST="/media/nmessier/NicksData/sda1"
DIRS=("Movies" "TV Shows")
```

---

### `verify_conversion.sh`

Verifies that every video file in the source has a corresponding `.mp4` in the destination. Reports matched, missing, and skipped (non-video) files per directory.

**Usage:**
```bash
./verify_conversion.sh
```

**Configuration** (edit variables at top of script):
```bash
SRC="/data/plex_data"
DST="/media/nmessier/NicksData/sda1"
DIRS=("Movies" "TV Shows")
```

---

### `audit_conversion.sh`

Audits a completed conversion job to find files needing attention before backing up.

**Features:**
- Parses conversion logs for `[ERROR] FFmpeg failed` entries
- Finds source `.mkv` files with no matching `.mp4` output (pending/failed/missed)
- Scans for non-MKV video files the conversion script never touches (`.avi`, `.divx`, `.mov`, etc.)
- Reports file sizes for everything found
- Optionally generates `cp` commands to copy problem files to an external drive
- Saves an audit report alongside the log file

**Usage:**
```bash
./audit_conversion.sh
```

The script prompts for:
1. Path to the conversion log file
2. Source directory (original video files)
3. Output directory (converted MP4 files)
4. Optional: external drive mount point for copy commands

---

## Recommended Workflows

### Converting the movie library
```bash
tmux new -s movies
./convert_mkv_to_mp4.sh --preset=medium
```

### Converting the TV show library
```bash
# Plan chunks (respects show folder boundaries)
./convert_mkv_to_mp4.sh --plan --preset=fast --hours=12

# Run one chunk at a time
tmux new -s chunk1
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
```

### Full pipeline
```bash
# 1. Convert
./convert_mkv_to_mp4.sh --preset=fast

# 2. Verify
./verify_conversion.sh

# 3. Sync (dry-run first)
./sync_converted.sh --dry-run
./sync_converted.sh

# 4. Audit any issues
./audit_conversion.sh
```

---

## Dependencies

```bash
sudo apt install ffmpeg bc

# Optional: VAAPI hardware acceleration (Intel GPU)
sudo apt install vainfo intel-media-va-driver-non-free
```
