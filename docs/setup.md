# Deployment Guide

Step-by-step guide for deploying the media server scripts on a new Linux media server.

---

## Prerequisites

Before you begin, make sure you have:

- **Linux Mint 22.2** (or any Ubuntu-based distro — Ubuntu 24.04, Pop!_OS, etc.)
- **Root/sudo access** on the target machine
- **Git** installed (`sudo apt install git`)
- **Two internal drives** — one for live media, one for archive/backup (recommended)
- **Network access** for downloading packages and reaching APIs (weather, ESPN, etc.)

---

## 1. Clone the Repository

```bash
cd ~
git clone https://github.com/YOUR_USER/bin.git
cd bin
```

> All scripts expect to live at `~/bin/`. If you clone elsewhere, update `BIN_DIR` in `config.env` accordingly.

---

## 2. Create Your Configuration File

Copy the example config and fill in your values:

```bash
cp config.env.example config.env
```

`config.env` is git-ignored and will never be pushed to GitHub. Every script in this repo sources it for paths, drive locations, and settings.

### Configuration Sections

Open `config.env` in your editor and fill in each section:

#### User & Paths

```bash
USERNAME="nmessier"              # Your Linux username
HOME_DIR="/home/your_user"        # Home directory
BIN_DIR="/home/your_user/bin"     # Where this repo is cloned
```

#### Media Library

```bash
MEDIA_SOURCE="/path/to/media"           # Root path to your Plex/ErsatzTV media
MEDIA_DIRS=("Movies" "TV Shows")         # Subdirectories within MEDIA_SOURCE
```

These are the directories Plex and ErsatzTV will read from.

#### Drive Mounts

```bash
DATA_DRIVE_PATH="/data"                          # Primary data drive (where media lives)
ARCHIVE_DRIVE_PATH="/archive"                    # Second internal drive for nightly sync
EXTERNAL_DRIVE_DEV="/dev/sda2"                   # External USB drive device
EXTERNAL_DRIVE_MOUNT="/mnt/external"             # Where the external drive gets mounted
EXTERNAL_DRIVE_MEDIA="/mnt/external/media"       # Media path on external drive
```

#### Backup (archive.sh)

```bash
BACKUP_SOURCE="/data/"                           # What to back up (trailing slash = contents)
BACKUP_STAGING="/archive/nicks_data"             # Local backup destination
BACKUP_EXTERNAL_TARGET="/mnt/external/backup"    # External drive target
BACKUP_LOG_DIR="/var/log/archive"                # Log directory
BACKUP_RETENTION_DAYS=30                         # Days of logs to keep
```

#### Conky Dashboard

```bash
WEATHER_STATION="KXXX"                   # NWS weather station ID
WEATHER_LOCATION="Your City ST"            # Display label for weather

SPORTS_TEAM="BOS"                        # ESPN team abbreviation
SPORTS_TEAM_NAME="Celtics"               # Display name
SPORTS_LEAGUE="nba"                      # League (nba, nfl, etc.)

CONKY_TIMEZONES="America/New_York:Eastern,America/Chicago:Central,America/Denver:Mountain,America/Los_Angeles:Pacific"

CONKY_DATA_DISK="/data"                  # Disk paths shown in conky system panel
CONKY_ARCHIVE_DISK="/archive"
CONKY_EXTERNAL_DISK="/mnt/external"
```

Find your weather station at https://api.weather.gov/stations.

#### Services

```bash
PLEX_SERVICE="plexmediaserver"           # Plex systemd service name
ERSATZTV_CONTAINER="ersatztv"            # ErsatzTV Docker container name
MINECRAFT_SERVICE="minecraft.service"    # Optional game server
PIHOLE_ENABLED=true                      # Whether Pi-hole is running on this host
```

---

## 3. Install System Dependencies

```bash
# Core tools (video conversion)
sudo apt install ffmpeg bc

# Optional: VAAPI hardware acceleration (Intel GPU)
sudo apt install vainfo intel-media-va-driver-non-free

# Optional: NVIDIA hardware acceleration (NVENC + NVDEC)
sudo apt install nvidia-driver-535 nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Lift the consumer NVENC 3-session limit (recommended for multi-channel ErsatzTV + Plex):
sudo ~/bin/gpu/nvidia-patch-update.sh
# Smoke-test concurrent NVENC sessions:
~/bin/gpu/nvenc-session-test.sh 5

# Conky desktop dashboard
sudo apt install conky-all jq curl lm-sensors

# Recommended utilities
sudo apt install tmux ncdu rsync smartmontools
```

Docker is required for ErsatzTV — see [ersatztv.md](ersatztv.md) for Docker installation. After installing the NVIDIA driver + container toolkit, both [Plex](plex.md#hardware-transcoding-nvidia-nvencnvdec) and [ErsatzTV](ersatztv.md#hardware-transcoding) can offload transcoding to the GPU; see those pages for the per-service config.

---

## 4. Set Up the Backup Cron Job

The backup system uses `rsync` to sync your data drive to the archive drive every night at 2 AM.

```bash
cd ~/bin/backup/

# Install the cron job (must run as root)
sudo bash setup_cron.sh

# Verify it was installed
sudo crontab -l
```

Create the log directory if it does not already exist:

```bash
sudo mkdir -p /var/log/archive
```

Test a manual run:

```bash
sudo bash archive.sh
```

See [backup/README.md](../backup/README.md) for full details on `--export` mode and log management.

---

## 5. Set Up the Conky Dashboard

The conky installer handles everything — dependencies, config deployment, cron jobs, and autostart:

```bash
cd ~/bin/conky/
./install.sh
```

This will:
1. Install `conky-all`, `jq`, `curl`, `lm-sensors`
2. Check for the JetBrainsMono Nerd Font
3. Copy conky configs to `~/.config/conky/`
4. Add cron jobs for weather (every 20 min) and sports (every 30 min)
5. Fetch initial data so the dashboard has content immediately
6. Create XDG autostart entries so both panels launch on login

If you need the font:
```bash
# Download JetBrainsMono Nerd Font from https://www.nerdfonts.com/font-downloads
# Extract to ~/.local/share/fonts/ and run:
fc-cache -fv
```

---

## 6. Set Up the Conversion Pipeline

The conversion scripts ensure all media files are in direct-play-compatible MP4 format (H.264 video, AAC audio). No Plex transcoding needed.

```bash
cd ~/bin/conversion/

# Plan the conversion in manageable chunks (~12-hour runs)
./convert_mkv_to_mp4.sh --plan --preset=fast

# Run chunk 1 inside tmux (so it survives SSH disconnects)
tmux new -s convert
./convert_mkv_to_mp4.sh --chunk=1 --preset=fast
# Ctrl+B then D to detach
```

After conversion completes:

```bash
# Verify all files converted successfully
./verify_conversion.sh

# Preview the sync
./sync_converted.sh --dry-run

# Run the sync (copies converted files back, removes originals)
./sync_converted.sh

# Audit for any remaining issues
./audit_conversion.sh
```

See [conversion/README.md](../conversion/README.md) for all options including hardware acceleration and parallel processing.

---

## 7. Set Up Media Server Components

Each component has its own detailed guide:

| Component | Guide |
|-----------|-------|
| Plex Media Server | [plex.md](plex.md) |
| ErsatzTV (live TV channels) | [ersatztv.md](ersatztv.md) |
| Pi-hole (DNS ad blocking) | [pihole.md](pihole.md) |

Install them in this order:
1. **Plex** — the core media server
2. **ErsatzTV** — creates live TV channels from your Plex library
3. **Pi-hole** — network-wide ad blocking (optional but recommended)

---

## 8. Verify Everything Works

Run through this checklist after setup is complete:

### Services

```bash
# Plex
sudo systemctl status plexmediaserver

# ErsatzTV
docker ps | grep ersatztv

# Pi-hole
sudo systemctl status pihole-FTL

# Backup cron
sudo crontab -l | grep archive
```

### Web Interfaces

| Service | URL |
|---------|-----|
| Plex | http://localhost:32400/web |
| ErsatzTV | http://localhost:8409 |
| Pi-hole | http://localhost/admin |

### Conky Dashboard

The dashboard should launch automatically on login. If not:

```bash
conky -c ~/.config/conky/conky-clock.conf -d
conky -c ~/.config/conky/conky-system.conf -d
```

### Backup

```bash
# Check last night's log
cat /var/log/archive/archive_$(date '+%Y-%m-%d').log
```

### Drive Health

```bash
# Quick SMART check on both drives
sudo smartctl -a /dev/sda | grep -E "Reallocated|Current_Pending|Offline_Uncorrectable"
sudo smartctl -a /dev/sdb | grep -E "Reallocated|Current_Pending|Offline_Uncorrectable"
```

---

## Tips

- **Always use tmux for long-running jobs over SSH** — conversion, sync, and verify can take hours:
  ```bash
  tmux new -s jobname       # Start session
  # run your script
  # Ctrl+B then D           # Detach (job keeps running)
  tmux attach -t jobname    # Re-attach later
  tmux ls                   # List sessions
  ```

- **Check disk space before large operations:**
  ```bash
  df -h /data /archive
  ```

- **Monitor drive health regularly** — both Seagate Enterprise drives have ~5 years of runtime. Run extended SMART tests monthly:
  ```bash
  sudo smartctl -t long /dev/sda
  sudo smartctl -t long /dev/sdb
  ```
