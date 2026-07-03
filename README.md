# Media Server Scripts

Utility scripts for a Linux media server running Plex, ErsatzTV, and Pi-hole
with automated video conversion, nightly backups, and a conky desktop dashboard.

Designed to be cloned onto a new server and configured via a single `config.env` file.

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> ~/bin
cd ~/bin

# 2. Create your config
cp config.env.example config.env
$EDITOR config.env   # Fill in your paths, drives, and preferences

# 3. Install dependencies
sudo apt install ffmpeg bc conky-all jq curl lm-sensors tmux ncdu

# 4. Set up components (see individual READMEs)
cd conky && ./install.sh        # Desktop dashboard
cd backup && sudo bash setup_cron.sh  # Nightly backups
```

See [docs/setup.md](docs/setup.md) for a full deployment walkthrough.

---

## Tools

| Directory | Description | Details |
|-----------|-------------|---------|
| [`conversion/`](conversion/) | Video conversion pipeline — batch convert, sync, verify, and audit video files for Plex/ErsatzTV direct play | [README](conversion/README.md) |
| [`backup/`](backup/) | Nightly rsync backup with optional external drive export and cron setup | [README](backup/README.md) |
| [`conky/`](conky/) | Desktop dashboard widgets — clock/weather, sports/betting dashboard, system stats (incl. live GPU NVENC/NVDEC counters) | [README](conky/README.md) |
| [`gpu/`](gpu/) | NVIDIA GPU helpers — keylase NVENC session-limit patch wrapper and concurrent-session smoke test | [README](gpu/README.md) |
| [`sports-betting-advisor/`](sports-betting-advisor/) | Data-driven NBA/NFL betting analysis with live stats and DraftKings odds | [README](sports-betting-advisor/README.md) |
| [`starrupture-server/`](starrupture-server/) | Dockerized StarRupture dedicated game server (App ID `3809400`, runs via Wine on Linux) | [README](starrupture-server/README.md) |
| [`docs/`](docs/) | Setup guides for Plex, ErsatzTV, Pi-hole, and deployment | [README](docs/README.md) |

---

## Configuration

All server-specific settings (paths, drives, services, preferences) are stored in
`config.env` at the repo root. This file is **git-ignored** and never pushed to GitHub.

```bash
cp config.env.example config.env
```

See [`config.env.example`](config.env.example) for all available settings with descriptions.

For server-specific notes (hardware, drive serials, health status), create a local
`SERVER_INFO.md` — this is also git-ignored.

---

## Dependencies

```bash
# Video conversion
sudo apt install ffmpeg bc

# Optional: VAAPI hardware acceleration (Intel GPU)
sudo apt install vainfo intel-media-va-driver-non-free

# Optional: NVIDIA hardware acceleration (NVENC + NVDEC)
sudo apt install nvidia-driver-535 nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Then optionally lift the consumer NVENC session-limit (3 -> unlimited):
sudo ~/bin/gpu/nvidia-patch-update.sh

# Conky desktop widgets
sudo apt install conky-all jq curl lm-sensors

# Sports betting advisor
pip install -r sports-betting-advisor/requirements.txt

# Recommended
sudo apt install tmux ncdu
```

---

## Tips

**Always use tmux for long-running jobs over SSH:**
```bash
tmux new -s jobname      # Start new session
# run your script
# Ctrl+B then D          # Detach (job keeps running)
tmux attach -t jobname   # Re-attach later
tmux ls                  # List all active sessions
```
