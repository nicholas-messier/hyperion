# Hyperion Server Scripts

Utility scripts for **Hyperion** — a high-end Linux media server running Mint 22.2, 
managing a Plex/ErsatzTV library with MKV-to-MP4 conversion and automated backups.

---

## Scripts

### `convert_mkv_to_mp4.sh`
Batch converts `.mkv` files to `.mp4` (H.264/AAC) for direct play compatibility on
Plex, ErsatzTV, and iPhone without transcoding.

**Features:**
- Smart stream copying — only re-encodes what needs to change (fast!)
- Handles 10-bit HEVC/x265 correctly (converts pixel format for libx264)
- Preserves ALL audio tracks (all languages, commentary, etc.)
- Preserves folder structure in output directory
- Skips already-converted files — safe to resume after interruption
- Rolling ETA that updates after every completed file
- Chunk planner splits large libraries into ~12hr runs without splitting a show mid-way
- Full log written to output directory

**Usage:**
```bash
# Basic run (medium preset)
./convert_mkv_to_mp4.sh

# TV shows — faster preset saves days on large libraries
./convert_mkv_to_mp4.sh --preset=fast

# Generate a chunk plan for a large library (~12hr chunks by default)
./convert_mkv_to_mp4.sh --plan --preset=fast

# Generate chunks targeting a specific duration
./convert_mkv_to_mp4.sh --plan --hours=8 --preset=fast

# Run a specific chunk
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
```

**Preset options:** `slow` | `medium` (default) | `fast` | `faster` | `veryfast`

**Recommended workflow for large TV libraries:**
```bash
# Step 1 — generate chunk plan
./convert_mkv_to_mp4.sh --plan --preset=fast

# Step 2 — run each chunk in a separate tmux session
tmux new -s chunk1
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
```

**Dependencies:** `ffmpeg`, `ffprobe`, `bc`
```bash
sudo apt install ffmpeg bc
```

---

### `archive.sh`
Nightly sync between local drives with optional export to an external USB drive.

**Features:**
- Local rsync sync between source and staging/archive drive
- Optional `--export` flag to copy to external Seagate Expansion HDD
- Auto-mounts and **auto-unmounts** external drive after export
- Disk space check before export — aborts cleanly if not enough space
- Full logging to `/var/log/archive/` with 30-day retention
- Clean error handling and exit trapping

**Usage:**
```bash
# Local sync only (what cron runs nightly)
sudo bash archive.sh

# Local sync + copy to external drive
sudo bash archive.sh --export
```

**Configuration** (edit top of script):
```bash
SOURCE="/data/"
STAGING="/archive/nicks_data"
EXTERNAL_DEV="/dev/sda2"
MOUNT_POINT="/mnt/your-drive-mount-point"
```

---

### `setup_cron.sh`
One-time setup script that installs `archive.sh` as a nightly cron job at 2:00 AM.

**Usage:**
```bash
sudo bash setup_cron.sh
```

**To verify the cron job was installed:**
```bash
sudo crontab -l
```

**To check last night's log:**
```bash
cat /var/log/archive/archive_$(date '+%Y-%m-%d').log
```

---

## Server Info

| Component | Details |
|-----------|---------|
| **Hostname** | hyperion |
| **OS** | Linux Mint 22.2 |
| **CPU** | High-end (12+ cores) |
| **Media drives** | 2x Seagate Enterprise 8TB (ST8000NM0055) |
| **Media server** | Plex + ErsatzTV |
| **Library** | ~215 movies, ~5135 TV episodes |

---

## Tips

**Always run long jobs inside tmux** to survive SSH disconnects:
```bash
sudo apt install tmux
tmux new -s convert
# run your script
# if disconnected, re-attach with:
tmux attach -t convert
```

**Check drive health before any RAID/NAS work:**
```bash
sudo smartctl -t long /dev/sda
sudo smartctl -t long /dev/sdb
# check results after ~13 hours
sudo smartctl -a /dev/sda
sudo smartctl -a /dev/sdb
```
