# GPU Tools

Helpers for managing the NVIDIA GPU used by Plex, ErsatzTV, and the conversion scripts. Designed for an NVIDIA GeForce GTX 1050 Ti (Pascal, GP107, 4GB) on driver 535.288.01, but should also work on newer Pascal/Turing/Ampere/Ada cards on supported drivers.

---

## Why this exists

After upgrading from an Intel/AMD GPU to a NVIDIA card, three things needed attention:

1. **NVIDIA drivers + nvidia-container-toolkit** must be installed on the host so Plex (native) and ErsatzTV (Docker) can both reach the GPU.
2. **Consumer NVIDIA cards limit concurrent NVENC encode sessions to 3.** The 4th caller fails with `OpenEncodeSessionEx failed: out of memory (10)`. With ErsatzTV running multiple always-on channels and Plex transcoding for remote clients, this ceiling is realistic to hit. The popular [keylase/nvidia-patch](https://github.com/keylase/nvidia-patch) flips one byte in `libnvidia-encode.so` to remove the cap (matches Quadro/Pro behavior). It must be re-applied after every driver upgrade.
3. **Visibility.** Without monitoring you can't tell when sessions are saturating, when transcodes silently fall back to CPU, or whether a workload is actually using NVENC vs hitting NVDEC.

---

## Scripts

### `nvidia-patch-update.sh`

Idempotent wrapper around `keylase/nvidia-patch`. Apply it on first install and after every driver upgrade.

```bash
# Apply (or re-apply) the patch
sudo ~/bin/gpu/nvidia-patch-update.sh

# Show current patch state (PATCHED / NOT PATCHED) without changing anything
sudo ~/bin/gpu/nvidia-patch-update.sh --status

# Restore the original (unpatched) library
sudo ~/bin/gpu/nvidia-patch-update.sh --rollback
```

What it does:
- Clones (or pulls) `https://github.com/keylase/nvidia-patch` into `/opt/nvidia-patch`
- Detects the running driver version with `nvidia-smi`
- Verifies the version is in the patch's supported list (run `bash /opt/nvidia-patch/patch.sh -l` to see all)
- Calls `patch.sh` to back up the original `libnvidia-encode.so.<ver>` to `/opt/nvidia/libnvidia-encode-backup/` and patch the live library
- Compares SHA1s of the patched lib vs the backup to print `PATCHED` / `NOT PATCHED`

### `nvenc-session-test.sh`

Smoke test for the session limit. Spawns N concurrent `ffmpeg h264_nvenc` jobs and reports how many succeed.

```bash
~/bin/gpu/nvenc-session-test.sh        # 5 sessions (default)
~/bin/gpu/nvenc-session-test.sh 8      # 8 sessions
```

Expected results:
- Unpatched GTX 1050 Ti: 3/N succeed, the rest fail with `OpenEncodeSessionEx failed: out of memory (10)`
- Patched: N/N succeed, encoder utilization climbs toward 100%

---

## Recommended driver-upgrade workflow

NVIDIA driver upgrades restore the original `libnvidia-encode.so`, undoing the patch. After any of:

- `sudo apt upgrade` that pulls a new `nvidia-driver-*`
- `apt-get dist-upgrade`
- Direct `.run` installer

…run:

```bash
sudo ~/bin/gpu/nvidia-patch-update.sh
sudo ~/bin/gpu/nvidia-patch-update.sh --status
```

If the driver version isn't yet supported by `keylase/nvidia-patch`, the wrapper exits with code 1 and tells you to check the supported-list. In that case stay on the patched older driver, or live with the 3-session cap until the upstream patch repo adds the new version.

---

## Verifying the GPU is actually being used

| Service     | How to check                                                                 |
|-------------|------------------------------------------------------------------------------|
| Plex        | Dashboard > Now Playing — transcode line shows `(hw)` for both decode + encode |
| Plex (cli)  | `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv` while a transcode is active should list `Plex Transcoder` |
| ErsatzTV    | While playing a channel: `ps -ef \| grep ffmpeg \| grep -v grep` shows `-hwaccel cuda -c:v h264_nvenc` and `nvidia-smi dmon -s u` shows `enc%` and `dec%` non-zero |
| Conversion  | Run `convert_mkv_to_mp4.sh --hwaccel=nvenc` against an HEVC source — `nvidia-smi dmon -s u` should report enc + dec activity, throughput should be ~10-15× realtime for 1080p |
| Conky       | Bottom of the system panel shows enc/dec/util in real time (added in this update) |

---

## Files

| Path | Purpose |
|------|---------|
| `nvidia-patch-update.sh` | Apply / status / rollback for the keylase NVENC session-limit patch |
| `nvenc-session-test.sh`  | Spawn N concurrent NVENC encodes and report success/failure |
| `/opt/nvidia-patch/`     | Cloned upstream patch repo (managed by the wrapper) |
| `/opt/nvidia/libnvidia-encode-backup/` | Original (unpatched) library, created by `patch.sh` on first run |
