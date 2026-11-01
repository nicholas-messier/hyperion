# Cloudflare Tunnel Setup Guide for IBD Tracker

This guide walks you through setting up a **100% free Cloudflare Tunnel** (`cloudflared`) on your home Linux server. 

With this setup:
- Your iPhone can push data from **home Wi-Fi or cellular 5G anywhere in the world** using a single HTTPS URL (e.g. `https://ibd.yourdomain.com`).
- **No router port forwarding** or firewall holes are needed.
- **No paid subscriptions** are required (Cloudflare Zero Trust Free Plan covers up to 50 users).
- **Automated SSL/TLS** encryption protects your clinical data in transit.

---

## Prerequisites

1. A free account on [Cloudflare](https://www.cloudflare.com/).
2. A domain name active on Cloudflare (you can register a cheap domain like `.com`, `.net`, `.xyz` directly inside Cloudflare Registrar for wholesale ~$8–$10/year, or add an existing domain by pointing its nameservers to Cloudflare).

---

## Step 1: Open Cloudflare Zero Trust Dashboard

1. Log in to [Cloudflare](https://dash.cloudflare.com/).
2. In the left-hand navigation sidebar, click **Zero Trust**.
3. If this is your first time opening Zero Trust, it will ask you to pick an organization name and select a plan (choose the **Free Plan**).

---

## Step 2: Create a Cloudflare Tunnel

1. Inside Zero Trust, go to **Networks** > **Tunnels** (or **Access** > **Tunnels**).
2. Click **Create a tunnel** (or **Add a tunnel**).
3. Select **Cloudflared** as the connector type and click **Next**.
4. Name your tunnel (e.g., `hyperion-ibd` or `home-server`) and click **Save tunnel**.

---

## Step 3: Copy Your Tunnel Token

1. Under the **Choose your environment** section, click on **Docker**.
2. Cloudflare will display a command with a long base64 token that looks like:
   ```bash
   docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token eyJh...
   ```
3. Copy **only the token string** after `--token` (the long string starting with `eyJh...`).

---

## Step 4: Configure Hostname Routing in Cloudflare

1. Click **Next** to proceed to the **Public Hostnames** tab (or edit the tunnel later and go to Public Hostnames).
2. Click **Add a public hostname**.
3. Fill in the fields:
   - **Subdomain:** `ibd` (or whatever prefix you prefer, e.g. `tracker`)
   - **Domain:** Select your domain from the dropdown (e.g. `yourdomain.com`)
   - **Path:** Leave blank
   - **Type:** Select `HTTP`
   - **URL:** Enter `ibd-tracker:8080` (this resolves directly across the Docker compose network) or `localhost:8080`
4. Click **Save hostname**.

---

## Step 5: Add Token to Server Environment

1. On your Linux server in the `ibd-tracker` directory, create or edit your `.env` file:
   ```bash
   cd /home/nmessier/bin/ibd-tracker
   cp .env.example .env   # if .env does not already exist
   ```
2. Set your API Key and Cloudflare Tunnel Token in `.env`:
   ```bash
   IBD_TRACKER_PORT=8080
   TIMEZONE=America/New_York
   IBD_TRACKER_API_KEY=your_secure_random_api_key_here
   CLOUDFLARE_TUNNEL_TOKEN=eyJh...your_token_from_step_3...
   ```

---

## Step 6: Start Services

Start both the IBD Tracker and the Cloudflare Tunnel container:

```bash
docker compose up -d
```

Check the logs to verify the tunnel connected:

```bash
docker compose logs -f cloudflared
```

You should see logs indicating:
```text
INF Connection registered with Cloudflare edge
INF Route online
```

---

## Step 7: Verify Access from Your iPhone

1. Open Safari on your iPhone (while connected to cellular data, off Wi-Fi).
2. Visit `https://ibd.yourdomain.com/health`.
3. You should see:
   ```json
   {"status":"ok"}
   ```
4. Visit `https://ibd.yourdomain.com/` to view your dashboard.
5. In your iOS Shortcut, set the base URL to `https://ibd.yourdomain.com` and provide your `X-API-Key` header (see [IOS_SHORTCUT_GUIDE.md](IOS_SHORTCUT_GUIDE.md)).
