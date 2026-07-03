# StarRupture Dedicated Server

Docker-based dedicated server for **StarRupture** (Creepy Jar, Early Access),
running the Windows server binary on Linux through Wine inside the
[`indifferentbroccoli/starrupture-server-docker`](https://github.com/indifferentbroccoli/starrupture-server-docker)
image.

Game App ID: `1631270` &nbsp;&nbsp;·&nbsp;&nbsp; Dedicated Server App ID: `3809400` (experimental)

> StarRupture's official dedicated server is a Windows-only experimental build.
> The container uses Wine. SteamCMD downloads are anonymous (no Steam account needed),
> but we run them OUTSIDE the container — see "Two important fixes" below.

---

## Files in this directory

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Defines the `starrupture` service, port mappings, DNS, and the `./server-files` bind mount |
| `.env.example` | Template for environment variables — copy to `.env` |
| `.env` | **git-ignored.** Real configuration including `ADMIN_PASSWORD` |
| `update.sh` | Runs SteamCMD on the host to install or update server files |
| `server-files/` | **git-ignored.** ~20 GB of Windows server install + your save games |
| `.steamcmd-state/` | **git-ignored.** SteamCMD cache (so re-runs are fast) |

---

## Two important fixes (why this isn't just `docker compose up -d`)

This setup deviates from the community Docker image's defaults in two ways
because of real bugs we hit on this host (Jun 2026):

### 1. `UPDATE_ON_START=false` — the in-container SteamCMD is broken

The `indifferentbroccoli` image bundles SteamCMD configured to write to
`/root`, which fails when it runs as the steam user (UID 1000). It exits
with `ERROR! Failed to install app '3809400' (Missing configuration)` —
a misleading message that actually means "SteamCMD can't write its own
config files". This loops forever on container restart.

Fix: we run SteamCMD ourselves from the clean `steamcmd/steamcmd:ubuntu-22`
image (via `./update.sh`) with a writable `HOME`, and tell the server
container `UPDATE_ON_START=false` so it just runs the existing files.

### 2. Explicit DNS servers in `docker-compose.yml`

This host has no `/etc/resolv.conf` (dangling symlink to systemd-resolved,
which isn't running on this machine; the host resolves DNS via
NetworkManager directly). Docker's embedded DNS resolver on user-defined
bridge networks has no upstream nameservers in that case, so Wine inside
the container can't resolve `api.epicgames.dev` and EOS session
registration fails silently.

Fix: `docker-compose.yml` pins `dns: [1.1.1.1, 8.8.8.8]`. You can
remove this if you fix the host's resolver setup.

---

## First-time setup

```bash
cd ~/bin/starrupture-server

# 1. Generate a strong admin password and put it in .env
openssl rand -base64 24
nano .env       # paste it into ADMIN_PASSWORD=

# 2. Install the ~20 GB of server files (one-time, takes ~15-30 min)
./update.sh

# 3. Start the server (first boot creates a new world named SESSION_NAME)
docker compose up -d

# 4. Watch the logs until you see "OnCreateSessionComplete GameSession 1"
docker compose logs -f starrupture
```

### After your first save

Once you've joined the server in-game and pressed **Esc → Save** to write
the first autosave, stop the server and flip the world-creation flags so
the world isn't regenerated on every restart:

```bash
docker compose down
nano .env       # set START_NEW_GAME=false and LOAD_SAVED_GAME=true
docker compose up -d
```

> **WARNING:** Leaving `START_NEW_GAME=true` after the world exists will
> overwrite your save on the next restart. This is the #1 cause of "my
> world disappeared" tickets in the community.

---

## Connecting from the game

1. Launch StarRupture on your PC
2. **Join Game → Dedicated Server**
3. Enter the server's public IP and `7777` (or LAN IP `192.168.0.16` for local testing)
4. If you set a `PLAYER_PASSWORD`, enter it; otherwise leave blank
5. Admin commands in-game: use the `ADMIN_PASSWORD` you set in `.env`

---

## Networking

### Ports

| Port | Protocol | Purpose | Forward on router? |
|------|----------|---------|---------------------|
| 7777 | UDP | Game traffic | **REQUIRED** |
| 27015 | UDP | Steam server browser query | Recommended (for public listing) |
| 7777 | TCP | In-game "Manage Server" tool | **NEVER expose to internet** |

This container intentionally does **not** map TCP 7777. With
`USE_DSSETTINGS=true` (default in our `.env`) all server config is loaded
from `DSSettings.txt`, so the TCP control channel isn't needed. Exposing
TCP 7777 publicly is a documented security risk and was the reason
`USE_DSSETTINGS` was added to the image.

### UFW / firewall

```bash
sudo ufw allow 7777/udp comment 'StarRupture game'
# UDP 27015 is already allowed on this host via the existing 27000:27015/udp rule
```

### Router port forwarding

Forward **external UDP 7777 → host UDP 7777** (and 27015 if you want the
server listed in the public browser). The host's LAN IP is `192.168.0.16`
and should be DHCP-reserved.

> StarRupture is reported to **not** work behind CGNAT or tunneling
> services like ngrok. If your ISP gives you a shared/CGNAT IP, players
> will not be able to connect from outside your LAN.

---

## Daily operations

```bash
# Status
docker compose ps

# Live logs
docker compose logs -f starrupture

# Restart (e.g. after editing .env)
docker compose restart starrupture

# Stop (graceful — save is flushed)
docker compose down

# Pull a newer game build from Steam (also pulls a newer image first)
./update.sh

# Disk usage of the install + saves
du -sh server-files/
```

### Where your save data lives

```
server-files/StarRupture/Saved/SaveGames/<SESSION_NAME>/
```

To back this up alongside the rest of the repo's archive workflow, point
`archive.sh` at `~/bin/starrupture-server/server-files/StarRupture/Saved/`.

### Updating the game

```bash
./update.sh           # stops the server, runs steamcmd, restarts it
./update.sh --no-stop # update without restarting (next manual restart will pick up changes)
```

`update.sh` validates the SteamCMD download, then verifies the server
executable exists before declaring success.

---

## Troubleshooting

**Container restart loops with `Could not find server executable`.**
The server files weren't downloaded. Run `./update.sh` from the host.

**`ERROR! Failed to install app '3809400' (Missing configuration)`.**
This is the in-container SteamCMD bug — make sure `UPDATE_ON_START=false`
in `.env` and use `./update.sh` instead.

**Logs spam `Could not resolve host: api.epicgames.dev`.** Container DNS
isn't reaching the internet. Confirm `dns:` is set in docker-compose.yml.
If you're running on a different host, change the DNS servers there.

**`LogGameSession: Warning: Autologin attempt failed`.** Harmless — a
separate EOS subsystem retry that doesn't affect dedicated-server
functionality. The session is created via `OnCreateSessionComplete` either
way; that's the line that matters.

**Server doesn't show up in the Steam server browser.** Either UDP 27015
isn't forwarded on your router, or you're behind CGNAT. Confirm with
`https://canyouseeme.org` for UDP 27015.

**Players get "connection timed out".** Almost always a port-forwarding
or CGNAT issue. Have one player connect from your LAN first to confirm
the server itself is reachable, then debug the WAN path.

**Save game disappeared after restart.** Check `.env` —
`START_NEW_GAME` should be `false` and `LOAD_SAVED_GAME` should be
`true` after the world has been created.

---

## References

- Official Creepy Jar guide: <https://creepyjar.theymes.com/hc/en/starrupture/articles/setting-up-a-star-rupture-dedicated-server-experimental-feature-using-the-steam-app-34>
- Docker image: <https://github.com/indifferentbroccoli/starrupture-server-docker>
- Unofficial wiki: <https://wiki.starrupture-utilities.com/en/dedicated-server/installation>
- DSSettings.txt reference: <https://wiki.starrupture-utilities.com/en/dedicated-server/configuration>
