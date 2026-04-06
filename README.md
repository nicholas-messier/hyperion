# Hyperion Server Scripts

Utility scripts for **Hyperion** — a high-end Linux media server running Mint 22.2,
managing a Plex/ErsatzTV library with automated video conversion, nightly backups,
and a conky desktop dashboard.

---

## Tools

| Directory | Description | Details |
|-----------|-------------|---------|
| [`conversion/`](conversion/) | Video conversion pipeline — batch convert, sync, verify, and audit video files for Plex/ErsatzTV direct play | [conversion/README.md](conversion/README.md) |
| [`backup/`](backup/) | Nightly rsync backup with optional external drive export and cron setup | [backup/README.md](backup/README.md) |
| [`conky/`](conky/) | Desktop dashboard widgets — clock, weather, Celtics schedule, system stats | [conky/README.md](conky/README.md) |
| [`sports-betting-advisor/`](sports-betting-advisor/) | Data-driven NBA/NFL betting analysis with live stats and DraftKings odds | [sports-betting-advisor/README.md](sports-betting-advisor/README.md) |

---

## Server Info

| Component | Details |
|-----------|---------|
| **Hostname** | hyperion |
| **OS** | Linux Mint 22.2 |
| **CPU** | 2x Intel Xeon E5-2620 v3 (24 threads @ 2.4GHz, VAAPI-capable) |
| **Media drives** | 2x Seagate Enterprise 8TB (ST8000NM0055) ~5 years runtime |
| **Backup drive** | Seagate Expansion 8TB (exFAT, external USB) |
| **Media server** | Plex + ErsatzTV |
| **Library** | ~235 movies (2.2TB), ~6300 TV episodes (4.4TB) |

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
# Video conversion
sudo apt install ffmpeg bc

# Optional: VAAPI hardware acceleration (Intel GPU)
sudo apt install vainfo intel-media-va-driver-non-free

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
