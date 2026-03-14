# Hyperion Server Scripts

Utility scripts for **Hyperion** — a high-end Linux media server running Mint 22.2,
managing a Plex/ErsatzTV library with automated MKV-to-MP4 conversion, nightly backups,
and conversion auditing.

---

## Scripts

### `convert_mkv_to_mp4.sh`
Batch converts `.mkv` files to `.mp4` (H.264/AAC) for direct play compatibility on
Plex, ErsatzTV, and iPhone without transcoding.

**Features:**
- Smart stream copying — only re-encodes what needs to change (saves hours on large libraries)
- Correctly handles **10-bit HEVC/x265** by converting pixel format for libx264
- Detects and handles **special characters in filenames** (spaces, parentheses, brackets) safely using bash arrays
- Preserves **ALL audio tracks** per-file (all languages, commentary tracks, etc.)
- Each audio track inspected individually — AAC tracks are copied, everything else (DTS, TrueHD, AC3, EAC3) re-encoded to AAC
- Preserves folder structure in output directory
- Skips already-converted files — safe to resume after interruption or failure
- Rolling ETA updated after every completed file using a 10-file rolling average
- **Chunk planner** splits large libraries into time-targeted runs without ever splitting a show mid-way through
- Configurable chunk target duration via `--hours` flag (default: 12 hours)
- `--preset` flag to tune encode speed vs compression — use `medium` for movies, `fast` for TV shows
- Full timestamped log written to output directory
- Shows space saved per file and total at summary

**Usage:**
```bash
# Basic run — prompts for source and output folders (medium preset)
./convert_mkv_to_mp4.sh

# Faster preset — recommended for large TV show libraries
./convert_mkv_to_mp4.sh --preset=fast

# Best compression — slowest, use for archival
./convert_mkv_to_mp4.sh --preset=slow

# Generate a chunk plan targeting ~12hr jobs (default)
./convert_mkv_to_mp4.sh --plan --preset=fast

# Generate a chunk plan targeting ~8hr jobs
./convert_mkv_to_mp4.sh --plan --hours=8 --preset=fast

# Run a specific chunk
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
./convert_mkv_to_mp4.sh --chunk=2 --preset=fast
```

**Preset options:** `slow` | `medium` (default) | `fast` | `faster` | `veryfast`

**Recommended workflow for large TV libraries (5000+ episodes):**
```bash
# Step 1 — generate chunk plan (probes sample files, takes a few minutes)
./convert_mkv_to_mp4.sh --plan --preset=fast

# Step 2 — run each chunk in a separate tmux session
tmux new -s chunk1
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast

# Detach with Ctrl+B then D, re-attach later with:
tmux attach -t chunk1
```

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

**Dependencies:** `ffmpeg`, `ffprobe`, `bc`
```bash
sudo apt install ffmpeg bc
```

---

### `archive.sh`
Nightly sync between local drives with optional export to an external USB drive.

**Features:**
- Local rsync sync from source to staging/archive directory using `--delete-delay` for safe deletions
- Optional `--export` flag to copy staged data to external Seagate Expansion HDD
- Auto-mounts external drive if not already mounted
- **Auto-unmounts** external drive after export completes (or if script fails mid-way)
- **Disk space check** before export — aborts cleanly with a clear error if not enough space
- Separate rsync log files for local and external transfers
- Full timestamped logging to `/var/log/archive/` with **30-day log retention**
- Colors suppressed automatically when running in cron (non-interactive)
- Clean exit trap handles unexpected failures gracefully

**Usage:**
```bash
# Local sync only (what cron runs nightly at 2 AM)
sudo bash archive.sh

# Local sync + copy to external Seagate drive
sudo bash archive.sh --export
```

**Configuration** (edit variables at top of script):
```bash
SOURCE="/data/"                  # What to back up
STAGING="/archive/nicks_data"    # Local backup destination (second internal drive)
EXTERNAL_DEV="/dev/sda2"         # External drive device
MOUNT_POINT="/mnt/your-mount"    # External drive mount point
RETENTION_DAYS=30                # How many days of logs to keep
```

**Check last night's run:**
```bash
cat /var/log/archive/archive_$(date '+%Y-%m-%d').log
```

---

### `setup_cron.sh`
One-time installer that registers `archive.sh` as a nightly cron job running at **2:00 AM**.

**Features:**
- Must be run as root (required for mount permissions in archive.sh)
- Detects if a cron job already exists and prompts before replacing
- Creates `/var/log/archive/` directory automatically
- Prints confirmation with schedule, paths, and usage instructions after install

**Usage:**
```bash
# Run once to install the cron job
sudo bash setup_cron.sh

# Verify it was installed
sudo crontab -l

# Remove it later if needed
sudo crontab -e
```

---

### `audit_conversion.sh`
Audits a completed (or in-progress) conversion job to find any files that need attention
before copying to an external drive for safe keeping.

**Features:**
- Parses the conversion log for any `[ERROR] FFmpeg failed` entries
- Cross-references every `.mkv` in the source directory against the output directory to find files with no matching `.mp4` (pending, failed, or missed)
- Scans source directory for **non-MKV video files** that the conversion script never touches: `.avi`, `.divx`, `.mov`, `.wmv`, `.m4v`, `.mpg`, `.mpeg`, `.ts`, `.vob`, `.xvid`, `.mp4`
- Reports file sizes for everything found
- Optionally generates ready-to-run `cp` commands to copy all problem files to an external drive
- Saves a full `audit_report_YYYYMMDD_HHMMSS.txt` alongside the log file

**Usage:**
```bash
chmod +x audit_conversion.sh
./audit_conversion.sh
```

The script prompts for:
1. Path to the conversion log file
2. Source directory (original video files)
3. Output directory (converted MP4 files)
4. Optional: external drive mount point for copy commands

**Example output:**
```
[ 1 ] FAILED CONVERSIONS (from log)
  FAILED   3.4 GB   28.Days.Later.2002.mkv

[ 2 ] MKV FILES NOT YET CONVERTED
  PENDING  33.0 GB  Doctor Sleep (2019).mkv

[ 3 ] NON-MKV VIDEO FILES (skipped by conversion script)
  AVI      850 MB   Django Unchained (2012).avi
  DIVX     700 MB   The Watchmen.divx
  MP4      2.4 GB   Fourth_of_July (2022).mp4

[ 4 ] SUGGESTED COPY COMMANDS FOR EXTERNAL DRIVE
  cp "/data/plex_data/Movies/Django Unchained (2012).avi" "/mnt/external/"
  ...
```

---

## Server Info

| Component | Details |
|-----------|---------|
| **Hostname** | hyperion |
| **OS** | Linux Mint 22.2 |
| **CPU** | High-end (12+ cores) |
| **Media drives** | 2x Seagate Enterprise 8TB (ST8000NM0055) ~5 years runtime |
| **Backup drive** | Seagate Expansion 8TB (exFAT, external USB) |
| **Media server** | Plex + ErsatzTV |
| **Library** | ~215 movies (2.2TB), ~5135 TV episodes (4.4TB) |

---

## Recommended Workflows

### Converting the movie library
```bash
tmux new -s movies
./convert_mkv_to_mp4.sh --preset=medium
# ~2 days on a high-end CPU for 215 mixed files
```

### Converting the TV show library
```bash
# Step 1 — plan chunks (respects show folder boundaries)
./convert_mkv_to_mp4.sh --plan --preset=fast --hours=12

# Step 2 — run one chunk at a time or stagger in separate tmux windows
tmux new -s chunk1
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
# ~5-8 days total for 5135 episodes
```

### Auditing after conversion
```bash
./audit_conversion.sh
# Point it at your log file and source/output directories
# Generates copy commands for anything that needs backing up
```

### Setting up nightly backups
```bash
# One-time setup
sudo bash setup_cron.sh

# Manual export to external drive any time
sudo bash archive.sh --export
```

### Always use tmux for long-running jobs over SSH
```bash
sudo apt install tmux

tmux new -s jobname      # Start new session
# run your script
# Ctrl+B then D          # Detach (job keeps running)
tmux attach -t jobname   # Re-attach later
tmux ls                  # List all active sessions
```

---

## Drive Health

Both drives are Seagate Enterprise ST8000NM0055 with ~43,000 hours runtime (~5 years).
Run extended SMART tests before any RAID or NAS migration:

```bash
# Start extended tests (~13 hours each)
sudo smartctl -t long /dev/sda
sudo smartctl -t long /dev/sdb

# Check results after completion
sudo smartctl -a /dev/sda
sudo smartctl -a /dev/sdb
```

**Known status:**
- Drive 1 (ZA1DF18Y): 1 historical UNC read error — monitor closely, plan to replace within 12 months
- Drive 2 (ZA1JJZ51): Clean error log — healthier of the two

---

## Dependencies

```bash
# Required for convert_mkv_to_mp4.sh
sudo apt install ffmpeg bc

# Required for archive.sh / setup_cron.sh
# rsync and cron are included in Mint 22.2 by default

# Recommended for long SSH sessions
sudo apt install tmux

# Recommended for interactive disk usage browsing
sudo apt install ncdu
```
