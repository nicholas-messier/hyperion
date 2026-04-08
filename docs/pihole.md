# Pi-hole

Guide for installing and configuring Pi-hole as the network DNS server on a Linux media server.

---

## What Is Pi-hole?

Pi-hole is a **network-wide ad blocker** that acts as a DNS sinkhole. Instead of installing ad blockers on every device, Pi-hole filters DNS requests for the entire network — blocking ads, trackers, and malware domains before they reach any device.

How it works:

1. Your router points all DNS queries to the Pi-hole server
2. Pi-hole checks each domain against its blocklists
3. Blocked domains return a null response (ads never load)
4. Allowed domains are forwarded to an upstream DNS resolver (e.g., Cloudflare, Google)

Every device on your network gets ad blocking automatically — phones, smart TVs, game consoles, IoT devices — without installing anything on them.

---

## Installation

Pi-hole is installed natively (not in Docker) using the official installer:

```bash
curl -sSL https://install.pi-hole.net | bash
```

This launches an interactive installer that walks you through:

1. **Network interface** — select your primary network adapter (usually `eth0` or `eno1`)
2. **Upstream DNS provider** — choose a resolver (Cloudflare `1.1.1.1`, Google `8.8.8.8`, etc.)
3. **Blocklists** — the default StevenBlack list is a good starting point
4. **Protocols** — enable both IPv4 and IPv6 (if your network uses IPv6)
5. **Static IP** — confirm or set a static IP for this server (critical — your DNS server cannot have a changing IP)
6. **Web admin interface** — install it (recommended)
7. **Web server (lighttpd)** — install it (required for the admin interface)
8. **Query logging** — enable (useful for debugging and stats)
9. **Privacy mode** — choose your preferred level

> **Important:** Note the admin password displayed at the end of installation. You can change it later with `pihole setpassword`.

---

## The Service

Pi-hole runs as `pihole-FTL.service` (FTL = Faster Than Light, the Pi-hole DNS engine).

### Service Management

```bash
# Check status
sudo systemctl status pihole-FTL

# Start the service
sudo systemctl start pihole-FTL

# Stop the service
sudo systemctl stop pihole-FTL

# Restart the service
sudo systemctl restart pihole-FTL

# Enable on boot (enabled by default after install)
sudo systemctl enable pihole-FTL

# View service logs
sudo journalctl -u pihole-FTL --since "1 hour ago"
```

---

## Web Admin Interface

The Pi-hole admin dashboard is accessible at:

```
http://localhost/admin
```

Or from any device on the network:

```
http://server-ip/admin
```

The dashboard shows:

- Total queries and percentage blocked
- Domains on blocklist count
- Query log (real-time DNS requests)
- Top blocked and permitted domains
- Client activity breakdown
- Query types over time graphs

### Set the Admin Password

```bash
# Set a new password
pihole setpassword

# Or set it non-interactively
pihole -a -p your_new_password
```

---

## Router Configuration

For Pi-hole to protect your entire network, configure your router to use the Pi-hole server as the DNS server.

### Steps

1. Log in to your router's admin panel (usually `192.168.1.1` or `192.168.0.1`)
2. Find the **DHCP / DNS settings** (often under LAN or Network settings)
3. Set the **Primary DNS** to the Pi-hole server's IP address (e.g., `192.168.1.100`)
4. Optionally set a **Secondary DNS** to a fallback (e.g., `1.1.1.1`) — though this means some queries will bypass Pi-hole
5. Save and reboot the router

> **Tip:** For maximum coverage, set Pi-hole as the **only** DNS server. If you add a secondary, devices may use it and bypass blocking. Alternatively, set the secondary to a second Pi-hole instance.

### Verify DNS Is Working

From any device on the network:

```bash
# Should resolve through Pi-hole
nslookup google.com server-ip

# Check if ad domains are blocked
nslookup ads.doubleclick.net server-ip
# Should return 0.0.0.0 or NXDOMAIN
```

---

## Common Commands

Pi-hole includes a full CLI for management:

```bash
# Check Pi-hole status
pihole status

# Enable Pi-hole (if temporarily disabled)
pihole enable

# Disable Pi-hole temporarily
pihole disable          # Disable indefinitely
pihole disable 5m       # Disable for 5 minutes
pihole disable 1h       # Disable for 1 hour

# Update gravity (blocklists) — pull latest block data
pihole -g

# Update Pi-hole itself
pihole -up

# View real-time query log
pihole -t

# Show summary stats
pihole -c              # Console dashboard (top-like view)

# Flush the DNS cache
pihole restartdns

# Query the Pi-hole database
pihole -q example.com  # Check if a domain is blocked

# Whitelist a domain
pihole -w example.com

# Blacklist a domain
pihole -b example.com

# Show version info
pihole -v
```

---

## Blocklists

### Default Blocklist

Pi-hole ships with the StevenBlack consolidated hosts list, which covers ads and trackers.

### Adding Custom Blocklists

1. Go to the web admin: **Group Management** > **Adlists**
2. Add a blocklist URL and click **Add**
3. Run `pihole -g` to update gravity with the new list

Popular additional blocklists:

| List | URL | Focus |
|------|-----|-------|
| StevenBlack Unified | `https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts` | Ads + malware (default) |
| OISD Big | `https://big.oisd.nl/` | Comprehensive blocking |
| Hagezi Multi Pro | `https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/hosts/pro.txt` | Ads, trackers, malware |
| Firebog Ticked Lists | See https://firebog.net/ | Curated collection |

### Whitelisting

Some sites break when certain domains are blocked. Whitelist them:

```bash
# Command line
pihole -w example.com

# Or via the web UI: Whitelist > Add Domain
```

Common domains that may need whitelisting:

- `s.youtube.com` — YouTube history
- `cdn.optimizely.com` — some site logins
- `clients4.google.com` — Android device setup
- Check https://discourse.pi-hole.net for community whitelist suggestions

---

## Logs

### Log Locations

| Log | Path | Contents |
|-----|------|----------|
| Pi-hole log | `/var/log/pihole/pihole.log` | DNS query log |
| FTL log | `/var/log/pihole/FTL.log` | FTL engine log (errors, startup) |
| FTL database | `/etc/pihole/pihole-FTL.db` | Long-term query database |

### Log Management

```bash
# View the query log in real time
pihole -t

# Flush the log (clears pihole.log)
pihole flush

# Check log file size
du -sh /var/log/pihole/pihole.log
```

Pi-hole rotates logs automatically via logrotate. The long-term database (`pihole-FTL.db`) can grow over time. To control its size, adjust the `MAXDBDAYS` setting:

```bash
# Edit FTL config
sudo nano /etc/pihole/pihole-FTL.conf

# Add or modify (default is 365 days)
MAXDBDAYS=90
```

Restart FTL after changes:

```bash
sudo systemctl restart pihole-FTL
```

---

## Conky Dashboard Integration

The conky system dashboard in this project monitors Pi-hole status automatically. The `conky-system.conf` panel shows:

- Whether `pihole-FTL.service` is running
- Service status indicator (active/inactive)

This is controlled by the `PIHOLE_ENABLED=true` setting in `config.env`. The conky dashboard checks the service status and displays it alongside Plex and ErsatzTV.

---

## Backup

### What to Back Up

```bash
# Pi-hole configuration
/etc/pihole/

# Key files within:
/etc/pihole/setupVars.conf        # Installation settings
/etc/pihole/pihole-FTL.conf       # FTL engine config
/etc/pihole/custom.list           # Local DNS records
/etc/pihole/adlists.list          # Blocklist URLs (or managed via DB)
```

### Built-In Teleporter

Pi-hole has a built-in backup/restore tool:

1. Go to **Settings** > **Teleporter** in the web admin
2. Click **Backup** to download a `.tar.gz` of all Pi-hole settings
3. To restore on a new install, upload the backup file on the Teleporter page

### Command-Line Backup

```bash
# Quick backup of the Pi-hole config directory
sudo tar czf /path/to/backup/pihole-config-$(date '+%Y-%m-%d').tar.gz /etc/pihole/
```

---

## Troubleshooting

### DNS Not Resolving

```bash
# Check if FTL is running
sudo systemctl status pihole-FTL

# Test DNS resolution directly against Pi-hole
dig @localhost google.com

# Check if port 53 is in use by another service
sudo ss -tlnp | grep :53

# On Ubuntu/Mint, systemd-resolved may conflict — disable it:
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
# Update /etc/resolv.conf to point to 127.0.0.1
```

### Web Interface Not Loading

```bash
# Check if lighttpd is running
sudo systemctl status lighttpd

# Restart it
sudo systemctl restart lighttpd

# Check if something else is using port 80
sudo ss -tlnp | grep :80
```

### High Memory Usage from FTL Database

```bash
# Check database size
du -sh /etc/pihole/pihole-FTL.db

# Reduce retention period
sudo nano /etc/pihole/pihole-FTL.conf
# Set MAXDBDAYS=30

sudo systemctl restart pihole-FTL
```

### Updating Pi-hole

```bash
# Update Pi-hole to the latest version
pihole -up
```

---

## Static IP Configuration

Pi-hole requires a static IP so devices always know where to send DNS queries. If you did not set one during installation:

### Using NetworkManager (Linux Mint default)

1. Open **Network Settings**
2. Click the gear icon on your wired connection
3. Go to the **IPv4** tab
4. Change method to **Manual**
5. Set your IP, netmask, gateway, and DNS
6. Save and reconnect

### Using the Command Line

```bash
# Check your current connection name
nmcli con show

# Set a static IP (replace values with your network info)
sudo nmcli con mod "Wired connection 1" \
  ipv4.addresses "192.168.1.100/24" \
  ipv4.gateway "192.168.1.1" \
  ipv4.dns "127.0.0.1" \
  ipv4.method manual

# Restart the connection
sudo nmcli con down "Wired connection 1"
sudo nmcli con up "Wired connection 1"
```

> **Note:** Set the DNS to `127.0.0.1` on the Pi-hole server itself so it uses its own DNS.
