# Backup Tools

Nightly automated backup pipeline for the Hyperion server. Syncs local drives via rsync
with optional export to an external USB drive.

---

## Scripts

### `archive.sh`

Nightly sync between local drives with optional export to an external USB drive.

**Features:**
- Local rsync sync from source to staging/archive directory using `--delete-delay` for safe deletions
- Optional `--export` flag to copy staged data to external Seagate Expansion HDD
- Auto-mounts external drive if not already mounted
- Auto-unmounts external drive after export completes (or if script fails mid-way)
- Disk space check before export — aborts cleanly with a clear error if not enough space
- Separate rsync log files for local and external transfers
- Full timestamped logging to `/var/log/archive/` with 30-day log retention
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
# Run once to install the cron job (from the backup/ directory)
cd backup/
sudo bash setup_cron.sh

# Verify it was installed
sudo crontab -l

# Remove it later if needed
sudo crontab -e
```

> **Note:** `setup_cron.sh` resolves the path to `archive.sh` relative to the current directory, so run it from within `backup/`.

---

## Dependencies

```bash
# rsync and cron are included in Linux Mint 22.2 by default
```
