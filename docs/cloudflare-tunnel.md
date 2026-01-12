# Cloudflare Tunnel Setup Guide

This guide explains how to use Cloudflare Tunnel to expose your DarkMatter Master Server
to the internet without port forwarding.

## Overview

Cloudflare Tunnel creates a secure, outbound-only connection from your computer to
Cloudflare's network. Slaves can then connect to your tunnel URL instead of your home IP.

**Benefits:**
- No port forwarding required
- Your home IP is hidden
- Free tier available
- Built-in DDoS protection

## Prerequisites

1. A Cloudflare account (free)
2. A domain added to Cloudflare (can use a free subdomain)
3. `cloudflared` CLI tool installed

## Installation

### Windows

1. Download cloudflared:
   - Go to https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
   - Download the Windows installer (cloudflared-windows-amd64.msi)
   - Run the installer

2. Or use winget:
   ```powershell
   winget install Cloudflare.cloudflared
   ```

### Linux

```bash
# Debian/Ubuntu
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-archive-keyring.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update
sudo apt install cloudflared

# Or download binary directly
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

## Quick Start (Temporary Tunnel)

For testing, you can create a quick tunnel without configuration:

```bash
# Start the DarkMatter Master Server first (port 8765)
# Then in a separate terminal:
cloudflared tunnel --url ws://localhost:8765

# Output will show something like:
# Your quick Tunnel has been created! Visit it at:
# https://random-words-here.trycloudflare.com
```

Use this URL in your slave .env:
```bash
DM_MASTER_HOST=random-words-here.trycloudflare.com
DM_CONNECTION_MODE=cloudflare
```

**Note:** Quick tunnels have a random URL that changes each time.

## Permanent Tunnel Setup

For a stable URL, create a named tunnel:

### 1. Login to Cloudflare

```bash
cloudflared tunnel login
# Opens browser to authenticate
```

### 2. Create a Tunnel

```bash
cloudflared tunnel create dm-master
# Note the tunnel ID shown
```

### 3. Configure the Tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: /path/to/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: dm.yourdomain.com
    service: ws://localhost:8765
  - service: http_status:404
```

### 4. Create DNS Record

```bash
cloudflared tunnel route dns dm-master dm.yourdomain.com
```

### 5. Run the Tunnel

```bash
cloudflared tunnel run dm-master
```

### 6. Configure Slaves

In slave .env:
```bash
DM_MASTER_HOST=dm.yourdomain.com
DM_CONNECTION_MODE=cloudflare
```

## Running as a Service

### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: At log on
4. Action: Start a program
5. Program: `cloudflared`
6. Arguments: `tunnel run dm-master`

### Linux (systemd)

```bash
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

## Troubleshooting

### Tunnel not connecting
```bash
# Check tunnel status
cloudflared tunnel info dm-master

# Test local server
curl http://localhost:8765/health
```

### WebSocket issues
Ensure your tunnel config uses `ws://` for WebSocket:
```yaml
ingress:
  - hostname: dm.yourdomain.com
    service: ws://localhost:8765
```

### Connection refused
Make sure the DarkMatter Master Server is running before starting the tunnel.

## Security Notes

1. **Secret Key**: Still use a strong secret key for HMAC authentication
2. **Tunnel Token**: Keep your tunnel credentials secure
3. **Access Policies**: Consider using Cloudflare Access for additional protection

## Free vs Paid

The free tier includes:
- Unlimited tunnels
- Unlimited bandwidth (fair use)
- Basic DDoS protection

Paid tiers add:
- Cloudflare Access (identity-based access control)
- Advanced security features
- Priority routing
