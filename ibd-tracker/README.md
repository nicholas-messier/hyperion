# IBD Bowel Movement & Symptom Tracker

A lightweight, self-hosted Crohn's and diverticulitis symptom tracker designed for 24/7 operation on Hyperion with zero bloat.

## Features

- **Ultra-Fast 3-Second iPhone Logging:** Native iOS Shortcut integration to log consistency (Bristol 1–7), pain scale (1–10), and blood presence (`none`, `some`, `alot`) with 3 taps from your lock screen or home screen.
- **Automated Aggregation:** Tracks daily movement counts, daily average Bristol consistency, pain progression, and blood events over time.
- **Doctor Analytics Dashboard:** Web-based dashboard with trends, charts, and a 1-click printable summary report formatted for GI visits with Dr. Vincent Aguirre and Dr. David Gould.
- **Dockerized & Persistent:** Runs in a minimal Docker container with SQLite database persistence under `./data`.

## Quick Start

```bash
cd ibd-tracker

# Build and start container
docker compose up -d

# Check logs
docker compose logs -f
```

Access the dashboard at `http://<hyperion-ip>:8080/`.

## Documentation

- [`PLAN.md`](PLAN.md) — Detailed technical specification and Devin CLI implementation blueprint.
- [`IOS_SHORTCUT_GUIDE.md`](IOS_SHORTCUT_GUIDE.md) — Step-by-step setup guide for the iOS Shortcut on iPhone (local queue & remote batch sync workflow).
- [`CLOUDFLARE_SETUP.md`](CLOUDFLARE_SETUP.md) — Zero-cost Cloudflare Tunnel guide for seamless local/remote iPhone data submission without port forwarding.
