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
    # Pin to a digest for reproducibility. Bump with:
    #   docker pull ghcr.io/ersatztv/ersatztv:latest
    #   docker images --digests ghcr.io/ersatztv/ersatztv | awk '$2=="latest"{print $3}'
    image: ghcr.io/ersatztv/ersatztv:latest@sha256:<digest>
    container_name: ersatztv
    environment:
      - TZ=America/New_York
      # NVIDIA passthrough — see "Hardware Transcoding" section below
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    ports:
      - "8409:8409"
    volumes:
      - /path/to/config:/config
      # IMPORTANT: quote both sides of the volume spec when the path has spaces.
      # Without quoting, Docker silently creates a literal "TV\Shows" directory in
      # the container, breaking all video reads (filler-only playback).
      - "/path/to/media/TV Shows:/data/media/TV Shows:ro"
      - /path/to/filler:/data/filler:ro
    tmpfs:
      - /transcode
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8409/iptv/channels.m3u >/dev/null || exit 1"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 60s
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

ErsatzTV supports hardware-accelerated transcoding for generating channel streams via VAAPI (Intel/AMD), NVENC (NVIDIA), and QSV (Intel Quick Sync). This server uses NVIDIA NVENC + NVDEC.

### NVIDIA (NVENC + NVDEC) — current setup

Prerequisites on the host:

```bash
# NVIDIA driver (Pascal-or-newer card, GTX 1050 Ti and up)
nvidia-smi

# nvidia-container-toolkit — injects NVIDIA libraries + devices into containers
sudo apt install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

The compose snippet above gives the container access via three pieces:
- `NVIDIA_VISIBLE_DEVICES=all` + `NVIDIA_DRIVER_CAPABILITIES=compute,video,utility`
- `deploy.resources.reservations.devices` block with `driver: nvidia` and `capabilities: [gpu]`
- The standard `ghcr.io/ersatztv/ersatztv:latest` image already ships with `ffmpeg --enable-nvenc --enable-nvdec --enable-cuda --enable-cuvid`. The CUDA libraries are injected at runtime by the toolkit, so no nvidia-specific image tag is required.

In the ErsatzTV web UI: **Settings > FFmpeg Profiles > [your profile]** > set **Hardware Acceleration: NVENC**.

### Recommended FFmpeg profile (1080p H.264 / GTX 1050 Ti)

| Field | Value | Why |
|-------|-------|-----|
| Hardware Acceleration | `NVENC` | Use the GPU encoder |
| Video Format | `H.264` | Broadest direct-play compatibility (Plex, iOS, Apple TV, Roku, etc.) |
| Bit Depth | `8` | Pascal NVENC H.264 is 8-bit only; matches the converted library |
| Resolution | `1920x1080` | Single profile for all current channels |
| Video Bitrate | `8000` kbps | Headroom for action scenes; CBR with bufsize=8000 |
| Video Profile | `high` | Better compression than baseline/main; supported by all modern decoders |
| Video Preset | `p4` | NVENC quality/speed balance preset (p1=fastest, p7=highest quality) |
| Allow B-Frames | ON | Pascal NVENC v6 supports H.264 B-frames; saves ~10% bitrate |
| Thread Count | `1` | NVENC doesn't need many CPU threads; reduces context-switch noise |
| Deinterlace | ON | Required for any interlaced filler/source |

These can be set directly via sqlite if you prefer scripted config:

```bash
# Stop the container first so EF Core writes commit cleanly
docker stop ersatztv
python3 - <<'EOF'
import sqlite3
c = sqlite3.connect('/path/to/ersatzTV/ersatztv.sqlite3')
c.execute("""UPDATE FFmpegProfile
             SET HardwareAcceleration=2,  -- Nvenc
                 VideoPreset='p4',
                 AllowBFrames=1,
                 ThreadCount=1,
                 VaapiDevice=NULL,
                 VaapiDriver=0,
                 VaapiDisplay=NULL
             WHERE Name='1920x1080 x264 aac';""")
c.commit()
EOF
docker start ersatztv
```

### Verification

```bash
# 1. Container can see the GPU
docker exec ersatztv nvidia-smi

# 2. ffmpeg in the container has NVENC encoders
docker exec ersatztv ffmpeg -hide_banner -encoders 2>&1 | grep -iE 'h264_nvenc|hevc_nvenc'

# 3. While a channel is playing, the actual ffmpeg command should use the full
#    CUDA pipeline. Look for "-hwaccel cuda -hwaccel_output_format cuda ... -c:v h264_nvenc":
ps -ef | grep ffmpeg | grep -v grep

# 4. nvidia-smi shows real encoder + decoder utilization (not just encoder):
nvidia-smi --query-gpu=utilization.encoder,utilization.decoder --format=csv

# 5. Conky's system panel (this repo) shows live GPU/NVENC/NVDEC stats.
```

### Common gotchas

- **`[WRN] Error detecting VAAPI capabilities` on every startup is harmless** when you're running NVENC. ErsatzTV always probes VAAPI at startup regardless of the configured method.
- **`h264_nvenc Could not open encoder` (exit -22) right after switching to NVENC** is usually a stale `VideoPreset` (empty string) or B-frame mismatch. Set Preset to `p4` and toggle Allow B-Frames.
- **3-session NVENC limit on consumer cards.** With 3 always-on channels + a Plex transcode, you can hit the cap. See [`gpu/README.md`](../gpu/README.md) and apply `nvidia-patch-update.sh` to remove it.
- **Volume mount paths with spaces must be quoted on both sides** in `ersatztv.yaml` (`"/host/TV Shows:/container/TV Shows:ro"`). Without quotes you'll silently get a `TV\Shows` directory inside the container and ErsatzTV will quietly serve idle filler instead of real video.

### VAAPI / Intel GPU (legacy)

If your server uses an Intel iGPU instead of NVIDIA, replace the `deploy.resources` block with `devices: ["/dev/dri:/dev/dri"]` and pick **Hardware Acceleration: VAAPI** in the FFmpeg profile. The rest of the workflow is the same.

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
