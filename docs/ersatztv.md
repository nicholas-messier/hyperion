# ErsatzTV

Guide for installing and configuring ErsatzTV on a Linux media server using Docker.

---

## What Is ErsatzTV?

ErsatzTV creates **custom live TV channels** from your existing media library. It schedules movies, TV episodes, and filler content into continuous channel streams — just like cable TV, but with your own content.

Key features:

- Build channels with schedules (e.g., "80s Movies", "Sitcom Night", "Saturday Morning Cartoons")
- Integrates with **Plex as an HDHomeRun tuner** — channels appear in the Plex Live TV & DVR guide
- Hardware transcoding support (VAAPI, NVENC, QSV)
- Web-based UI for channel management
- Reads directly from your existing media library (no duplication)

---

## Prerequisites

### Install Docker

If Docker is not already installed:

```bash
# Install Docker using the official convenience script
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (avoids needing sudo for docker commands)
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect, then verify
docker --version
docker compose version
```

> **Note:** `docker compose` (v2) is included with modern Docker installations. If you only have `docker-compose` (v1), the commands below still work — just use `docker-compose` instead of `docker compose`.

---

## Docker Compose Setup

### Create the Compose File

Create `ersatztv.yaml` (or add to your existing compose setup):

```yaml
services:
  ersatztv:
    image: ghcr.io/ersatztv/ersatztv
    container_name: ersatztv
    environment:
      - TZ=America/New_York
    devices:
      - /dev/dri:/dev/dri  # GPU passthrough for hardware transcoding
    ports:
      - "8409:8409"
    volumes:
      - /path/to/config:/config
      - /path/to/media:/data/media:ro
    tmpfs:
      - /transcode
    restart: unless-stopped
```

### Configure Volume Paths

Update the volume paths to match your `config.env` values:

| Compose Path | Maps To | Description |
|-------------|---------|-------------|
| `/path/to/config` | A persistent directory for ErsatzTV data (e.g., `/home/your_user/ersatztv-config`) | ErsatzTV database, settings, and channel configs |
| `/path/to/media` | Your `MEDIA_SOURCE` value from `config.env` (e.g., `/path/to/media`) | Your media library, mounted read-only |

Example with real paths:

```yaml
    volumes:
      - /home/your_user/ersatztv-config:/config
      - /path/to/media:/data/media:ro
```

### Environment and Devices

| Setting | Purpose |
|---------|---------|
| `TZ=America/New_York` | Sets the container timezone for accurate scheduling |
| `/dev/dri:/dev/dri` | Passes through the GPU for VAAPI hardware transcoding. Remove this line if you have no Intel/AMD GPU or do not want hardware transcoding |
| `tmpfs: /transcode` | Uses RAM for temporary transcode files — faster and avoids disk wear |
| `restart: unless-stopped` | Container auto-restarts on crash or server reboot (unless manually stopped) |

---

## Starting ErsatzTV

### First Launch

```bash
# Start in detached mode
docker compose -f ersatztv.yaml up -d

# Verify it's running
docker ps | grep ersatztv
```

### Management Commands

```bash
# Start the container
docker compose -f ersatztv.yaml up -d

# Stop the container
docker compose -f ersatztv.yaml down

# Restart the container
docker compose -f ersatztv.yaml restart

# View logs (follow mode)
docker compose -f ersatztv.yaml logs -f

# View last 100 lines of logs
docker compose -f ersatztv.yaml logs --tail 100

# Pull the latest image and recreate
docker compose -f ersatztv.yaml pull
docker compose -f ersatztv.yaml up -d

# Check container resource usage
docker stats ersatztv
```

---

## Web UI

Open a browser and navigate to:

```
http://localhost:8409
```

Or from another machine on the network:

```
http://server-ip:8409
```

The web UI is where you configure everything — media sources, channels, schedules, and playback settings.

---

## Initial Configuration

### 1. Add a Media Source

1. Go to **Media** > **Media Sources** in the web UI
2. Click **Add Media Source**
3. Choose **Local** as the source type
4. Browse to `/data/media` (this is the path *inside the container*, mapped from your `MEDIA_SOURCE`)
5. Add paths for each library:
   - `/data/media/Movies`
   - `/data/media/TV Shows`
6. Let ErsatzTV scan and index the media

### 2. Create a Channel

1. Go to **Channels** > **Add Channel**
2. Set a channel number (e.g., 1) and name (e.g., "Movies")
3. Configure the streaming mode:
   - **HLS** — recommended for Plex integration
   - **MPEG-TS** — lower latency, good for direct viewing
4. Set resolution and transcoding options (match your typical playback device)

### 3. Build a Schedule

1. Select your channel and go to **Schedule**
2. Add programming blocks:
   - Select a collection, show, or movie to schedule
   - Set playback order (shuffle, chronological, etc.)
   - Configure filler content for gaps (bumpers, trailers, etc.)
3. ErsatzTV will automatically generate a continuous stream

---

## Connecting to Plex

ErsatzTV emulates an **HDHomeRun tuner**, which Plex can use as a Live TV source.

### Add ErsatzTV as a Tuner in Plex

1. In Plex, go to **Settings** > **Live TV & DVR**
2. Click **Set Up Plex DVR** (or add another device if you already have one)
3. Plex should auto-discover ErsatzTV on the network. If not, enter the URL manually:
   ```
   http://server-ip:8409/iptv/tuner
   ```
4. Plex will detect the available channels
5. For the guide data, use the XMLTV endpoint:
   ```
   http://server-ip:8409/iptv/xmltv
   ```
6. Map channels to the guide data
7. Save and you are done — ErsatzTV channels now appear in the Plex Live TV guide

### Verify in Plex

Go to **Live TV & DVR** in Plex. You should see your custom channels in the guide with proper names and scheduling. Click a channel to watch the live stream.

---

## Configuration Data

All ErsatzTV configuration is stored in the `/config` volume mount:

```
/home/your_user/ersatztv-config/
├── ersatztv.db          # Main database (channels, schedules, settings)
├── logs/                # Application logs
└── ...
```

### Backup

Back up the config directory to preserve your channel configurations and schedules:

```bash
# Simple copy
cp -a /home/your_user/ersatztv-config/ /path/to/backup/ersatztv-config-$(date '+%Y-%m-%d')/
```

The media files themselves are not stored by ErsatzTV — it reads them from your Plex library via the read-only volume mount.

---

## Hardware Transcoding

ErsatzTV supports hardware-accelerated transcoding for generating channel streams.

### VAAPI (Intel GPU)

The compose file already passes through `/dev/dri` for VAAPI support. Verify it is working:

```bash
# On the host, check VAAPI is available
vainfo

# Inside the container
docker exec ersatztv vainfo
```

In the ErsatzTV web UI, go to **Settings** and enable VAAPI hardware acceleration.

### Troubleshooting GPU Access

If the container cannot access the GPU:

```bash
# Check device permissions on the host
ls -la /dev/dri/

# The container runs as a non-root user — you may need to adjust permissions
# or add the render group
sudo usermod -aG render $USER
```

---

## Updates

ErsatzTV is updated by pulling the latest Docker image:

```bash
# Pull the latest image
docker compose -f ersatztv.yaml pull

# Recreate the container with the new image
docker compose -f ersatztv.yaml up -d
```

Your configuration is preserved in the `/config` volume — only the application container is replaced.

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker compose -f ersatztv.yaml logs --tail 50

# Verify the config directory exists and is writable
ls -la /home/your_user/ersatztv-config/

# Check port availability
sudo ss -tlnp | grep 8409
```

### Media Not Showing Up

- Verify the volume mount path is correct in the compose file
- Check that the media directory is readable inside the container:
  ```bash
  docker exec ersatztv ls /data/media/
  ```
- Re-scan the media source in the web UI

### Plex Can't Find the Tuner

- Verify ErsatzTV is running: `docker ps | grep ersatztv`
- Test the tuner endpoint: `curl http://localhost:8409/iptv/tuner`
- Test the XMLTV endpoint: `curl http://localhost:8409/iptv/xmltv`
- Make sure Plex and ErsatzTV are on the same network
