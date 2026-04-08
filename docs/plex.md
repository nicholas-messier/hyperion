# Plex Media Server

Guide for installing and configuring Plex Media Server on a Linux media server (Linux Mint / Ubuntu).

---

## Overview

Plex Media Server organizes your video, music, and photo libraries and streams them to any device. On this server it runs as a systemd service under the `plex` user, serving a library of movies and TV shows stored on local drives.

---

## Installation

### Add the Plex APT Repository

```bash
# Import the Plex signing key
curl https://downloads.plex.tv/plex-keys/PlexSign.key | sudo gpg --dearmor -o /usr/share/keyrings/plex-archive-keyring.gpg

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/plex-archive-keyring.gpg] https://downloads.plex.tv/repo/deb public main" | \
  sudo tee /etc/apt/sources.list.d/plexmediaserver.list

# Update and install
sudo apt update
sudo apt install plexmediaserver
```

### Verify the Service

Plex installs as a systemd service that starts automatically:

```bash
sudo systemctl status plexmediaserver
```

You should see `active (running)`. The service runs as the `plex` user.

---

## Systemd Service

The Plex service is managed via systemd as `plexmediaserver.service`.

### Common Commands

```bash
# Check status
sudo systemctl status plexmediaserver

# Start the service
sudo systemctl start plexmediaserver

# Stop the service
sudo systemctl stop plexmediaserver

# Restart the service
sudo systemctl restart plexmediaserver

# Enable on boot (enabled by default after install)
sudo systemctl enable plexmediaserver

# Disable on boot
sudo systemctl disable plexmediaserver

# View recent logs
sudo journalctl -u plexmediaserver --since "1 hour ago"
```

### Service Details

| Property | Value |
|----------|-------|
| Service name | `plexmediaserver.service` |
| Runs as user | `plex` |
| Config directory | `/var/lib/plexmediaserver/Library/Application Support/` |
| Default port | `32400` |

---

## Configuration Data

All Plex configuration, databases, metadata, and cache live at:

```
/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/
```

Key subdirectories:

| Directory | Contents |
|-----------|----------|
| `Plug-in Support/Databases/` | The main Plex database (`com.plexapp.plugins.library.db`) |
| `Metadata/` | Downloaded artwork, posters, and metadata |
| `Media/` | Generated thumbnails and video preview frames |
| `Cache/` | Temporary cache (safe to delete) |
| `Preferences.xml` | Server settings (name, auth token, remote access, etc.) |

> **Permissions:** This directory is owned by the `plex` user. If Plex cannot read your media files, make sure the `plex` user has read access to your media directories.

---

## Initial Setup

### Web UI

Open a browser and navigate to:

```
http://localhost:32400/web
```

If setting up remotely over SSH, use an SSH tunnel:

```bash
ssh -L 32400:localhost:32400 user@server-ip
```

Then open `http://localhost:32400/web` on your local machine.

### First-Time Configuration

1. **Sign in** with your Plex account (or create one at https://www.plex.tv)
2. **Name your server** (e.g., "MediaServer")
3. **Add your media libraries** (see next section)
4. **Finish setup** — Plex will begin scanning your libraries

---

## Adding Media Libraries

Your media is stored at the path defined by `MEDIA_SOURCE` in `config.env`. The default structure:

```
/path/to/media/
├── Movies/
│   ├── Movie Name (2024)/
│   │   └── Movie Name (2024).mp4
│   └── ...
└── TV Shows/
    ├── Show Name/
    │   ├── Season 01/
    │   │   ├── Show Name - S01E01.mp4
    │   │   └── ...
    │   └── ...
    └── ...
```

### Add a Movie Library

1. Go to **Settings** > **Manage** > **Libraries** > **Add Library**
2. Choose **Movies** as the type
3. Click **Browse for media folder** and select your Movies directory (e.g., `/path/to/media/Movies`)
4. Configure the agent (default "Plex Movie" works well)
5. Click **Add Library**

### Add a TV Show Library

1. Go to **Settings** > **Manage** > **Libraries** > **Add Library**
2. Choose **TV Shows** as the type
3. Click **Browse for media folder** and select your TV Shows directory (e.g., `/path/to/media/TV Shows`)
4. Configure the agent (default "Plex TV Series" works well)
5. Click **Add Library**

### File Permissions

The `plex` user needs read access to your media directories:

```bash
# Option 1: Add plex to your user's group
sudo usermod -aG nmessier plex
sudo systemctl restart plexmediaserver

# Option 2: Set directory permissions
sudo chmod -R o+rx /path/to/media/

# Verify plex can read the files
sudo -u plex ls /path/to/media/Movies/
```

---

## Library Settings

### Scan Settings

Go to **Settings** > **Manage** > **Libraries**, click the three-dot menu on a library:

- **Scan Library Files** — triggers an immediate scan for new/changed files
- **Empty Trash** — permanently removes items marked for deletion
- **Clean Bundles** — removes leftover metadata for deleted items

### Scheduled Tasks

Go to **Settings** > **Manage** > **Libraries** > **Scan my library automatically**:

- Enable **Update my library automatically** — Plex watches for filesystem changes
- Enable **Run a partial scan when changes are detected** — faster incremental scans
- Enable **Update my library periodically** — fallback scheduled scan

### Optimization (Analyze Media)

After adding libraries, let Plex analyze your media:

1. Go to a library
2. Click **Manage Library** > **Analyze**

This generates audio and video fingerprints for better playback experience.

---

## Remote Access

To stream outside your local network:

1. Go to **Settings** > **Remote Access**
2. Click **Enable Remote Access**
3. Plex will attempt to automatically configure port forwarding via UPnP
4. If automatic setup fails, manually forward **port 32400** (TCP) on your router to the server's LAN IP
5. The status should show a green checkmark with "Fully accessible outside your network"

### Manual Port Forward

On your router, create a port forwarding rule:

| Setting | Value |
|---------|-------|
| External port | 32400 |
| Internal IP | Your server's LAN IP (e.g., 192.168.1.100) |
| Internal port | 32400 |
| Protocol | TCP |

### Verify Remote Access

Visit https://app.plex.tv from another network to confirm your server is reachable.

---

## Backup Considerations

### What to Back Up

The most critical data is the Plex database and preferences:

```bash
# The Plex database (contains all library metadata, watch history, playlists)
/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/

# Server preferences (auth token, server name, settings)
/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml
```

### Manual Database Backup

```bash
# Stop Plex to ensure a clean backup
sudo systemctl stop plexmediaserver

# Copy the database
sudo cp -a "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/" \
  /path/to/backup/plex-db-$(date '+%Y-%m-%d')/

# Restart Plex
sudo systemctl start plexmediaserver
```

### What You Can Skip

- `Cache/` — regenerated automatically
- `Media/` — preview thumbnails, regenerated on demand (but large and slow to regenerate)
- The media files themselves are backed up separately by `archive.sh`

---

## Media Format and the Conversion Pipeline

Plex works best when media files can be **direct played** without server-side transcoding. This means:

- **Video:** H.264 (8-bit)
- **Audio:** AAC
- **Container:** MP4

The `conversion/` scripts in this repo ensure your entire library is in this format:

```bash
cd ~/bin/conversion/

# Convert MKV/AVI/etc. to MP4 (H.264 + AAC)
./convert_mkv_to_mp4.sh --preset=fast

# Sync converted files back to the source library
./sync_converted.sh

# Verify everything converted
./verify_conversion.sh
```

This eliminates Plex transcoding for most clients (iPhone, Apple TV, Roku, web browser, etc.), reducing CPU load and enabling smooth playback on the Xeon hardware.

See [../conversion/README.md](../conversion/README.md) for full conversion pipeline documentation.

---

## Troubleshooting

### Plex Can't Find Media Files

```bash
# Check that the plex user can read the directories
sudo -u plex ls /path/to/media/Movies/

# If permission denied, add plex to the appropriate group
sudo usermod -aG nmessier plex
sudo systemctl restart plexmediaserver
```

### Service Won't Start

```bash
# Check logs for errors
sudo journalctl -u plexmediaserver -n 50

# Check if port 32400 is already in use
sudo ss -tlnp | grep 32400
```

### Remote Access Not Working

1. Verify port forwarding on your router
2. Check firewall:
   ```bash
   sudo ufw status
   sudo ufw allow 32400/tcp
   ```
3. Test from outside your network at https://app.plex.tv

### Database Corruption

If the Plex database becomes corrupt:

```bash
# Stop Plex
sudo systemctl stop plexmediaserver

# Repair the database
sudo -u plex sqlite3 "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db" "PRAGMA integrity_check;"

# If repair fails, restore from backup
sudo cp /path/to/backup/plex-db-YYYY-MM-DD/* \
  "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/"

sudo systemctl start plexmediaserver
```

---

## Updates

Plex updates are delivered via the APT repository:

```bash
sudo apt update
sudo apt upgrade plexmediaserver
```

The service restarts automatically after an upgrade.
