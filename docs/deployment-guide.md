# DarkMatter Deployment Guide

Complete guide for setting up distributed Master/Slave architecture with multiple connection modes.

## Table of Contents

1. [Connection Modes Overview](#1-connection-modes-overview)
2. [Master Server Setup (Windows)](#2-master-server-setup-windows)
3. [Slave Setup (Linux)](#3-slave-setup-linux)
4. [Relay Server Setup](#4-relay-server-setup)
5. [Cloudflare Tunnel Setup](#5-cloudflare-tunnel-setup)
6. [Environment Variables Reference](#6-environment-variables-reference)
7. [Troubleshooting](#7-troubleshooting)
8. [Security Best Practices](#8-security-best-practices)

---

## 1. Connection Modes Overview

DarkMatter supports three connection modes to link Slaves to the Master Server:

| Mode | Use Case | Requirements | NAT Friendly |
|------|----------|--------------|--------------|
| **Direct** | LAN or port-forwarded WAN | Master reachable by slaves | No |
| **Relay** | NAT traversal, multiple networks | VPS with public IP | Yes |
| **Cloudflare** | No port forwarding, hide home IP | Cloudflare account | Yes |

### Mode Selection Guide

```
┌─────────────────────────────────────────────────────────────────┐
│                    Which mode should I use?                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Master and Slaves on same LAN?                                  │
│    └─> YES: Use DIRECT mode                                      │
│    └─> NO: Continue below                                        │
│                                                                  │
│  Can you port forward on Master's network?                       │
│    └─> YES: Use DIRECT mode with port forwarding                 │
│    └─> NO: Continue below                                        │
│                                                                  │
│  Do you have a VPS/server with public IP?                        │
│    └─> YES: Use RELAY mode (deploy relay.py on VPS)              │
│    └─> NO: Use CLOUDFLARE mode                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture Diagrams

**Direct Mode:**
```
┌──────────────┐                    ┌──────────────┐
│   Master     │◄───── TCP ────────│    Slave     │
│  (Windows)   │      port 8765    │   (Linux)    │
└──────────────┘                    └──────────────┘
```

**Relay Mode:**
```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   Master     │ ──────> │    Relay     │ <────── │    Slave     │
│  (Windows)   │         │   (VPS)      │         │   (Linux)    │
│              │         │              │         │              │
│ Connects OUT │         │ Public IP    │         │ Connects OUT │
└──────────────┘         └──────────────┘         └──────────────┘
```

**Cloudflare Mode:**
```
┌──────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│   Master     │───>│ cloudflared │───>│ Cloudflare  │<───│    Slave     │
│  (Windows)   │    │  (tunnel)   │    │   Network   │    │   (Linux)    │
└──────────────┘    └─────────────┘    └─────────────┘    └──────────────┘
```

---

## 2. Master Server Setup (Windows)

The Master Server runs the GUI and controls all slave operations.

### Prerequisites

- Windows 10/11
- Python 3.10+
- DarkMatter installed and running

### Configuration Steps

#### Step 1: Generate Secret Key

1. Open DarkMatter application
2. Navigate to **Master Control** tab
3. Click **Generate** button to create a 64-character secret key
4. **Important:** Copy and save this key - all slaves need it

#### Step 2: Select Connection Mode

In the Master Control tab, select your connection mode:

**Direct Mode:**
- Select **Direct** in the mode selector
- **Host:** `0.0.0.0` (listen on all interfaces)
- **Port:** `8765` (default)
- **Secret:** Your generated key
- Click **START SERVER**

For WAN access, configure port forwarding on your router (port 8765 → your PC).

**Relay Mode:**
- Select **Relay** in the mode selector
- **Relay URL:** `your-relay-server.com:8765`
- **Secret:** Same key configured on relay server
- Click **CONNECT**

**Cloudflare Mode:**
- Select **Direct** mode and **START SERVER** (localhost:8765)
- Run cloudflared tunnel separately (see [Section 5](#5-cloudflare-tunnel-setup))
- Share the tunnel URL with slaves

#### Step 3: Verify Connection

Once running, check the status indicator:
- **Direct/Cloudflare:** "Running on 0.0.0.0:8765"
- **Relay:** "Connected to relay.example.com"

Connected slaves appear in the **Connected Slaves** list automatically.

---

## 3. Slave Setup (Linux)

Slaves are headless worker nodes running on Linux servers.

### Prerequisites

- Debian 11+ / Ubuntu 20.04+ / similar
- Python 3.10+
- Root/sudo access

### Automated Installation (Recommended)

The project includes an installation script:

```bash
# 1. Copy project files to your server (scp, git clone, etc.)
cd /path/to/darkmatter

# 2. Run installer as root
sudo ./deploy/install.sh
```

The installer will:
- Install system dependencies (python3, python3-venv)
- Create `dm-slave` system user
- Set up `/opt/dm-trafficbot` directory
- Create Python virtual environment
- Install systemd service

### Manual Installation

```bash
# 1. Install dependencies
sudo apt update
sudo apt install python3 python3-venv python3-pip

# 2. Create service user
sudo useradd -r -s /usr/sbin/nologin -d /opt/dm-trafficbot dm-slave

# 3. Create install directory
sudo mkdir -p /opt/dm-trafficbot
sudo chown dm-slave:dm-slave /opt/dm-trafficbot

# 4. Copy project files
sudo cp -r core/ slave.py requirements.txt /opt/dm-trafficbot/
sudo cp -r deploy/ /opt/dm-trafficbot/
sudo mkdir -p /opt/dm-trafficbot/resources

# 5. Setup virtual environment
cd /opt/dm-trafficbot
sudo -u dm-slave python3 -m venv .venv
sudo -u dm-slave .venv/bin/pip install -r requirements.txt

# 6. Set ownership
sudo chown -R dm-slave:dm-slave /opt/dm-trafficbot
```

### Configuration (.env file)

Create `/opt/dm-trafficbot/.env`:

```bash
sudo nano /opt/dm-trafficbot/.env
```

**Direct Mode Configuration:**
```bash
# Connection settings
DM_MASTER_HOST=192.168.1.100
DM_MASTER_PORT=8765
DM_CONNECTION_MODE=direct

# Authentication (MUST match Master's secret key)
DM_SECRET_KEY=your-64-character-secret-key-from-master-gui

# Slave identification
DM_SLAVE_NAME=slave-01

# Logging (DEBUG, INFO, WARNING, ERROR)
DM_LOG_LEVEL=INFO
```

**Relay Mode Configuration:**
```bash
DM_MASTER_HOST=relay.yourserver.com
DM_MASTER_PORT=8765
DM_CONNECTION_MODE=relay
DM_SECRET_KEY=your-64-character-secret-key
DM_SLAVE_NAME=slave-01
DM_LOG_LEVEL=INFO
```

**Cloudflare Mode Configuration:**
```bash
DM_MASTER_HOST=random-words.trycloudflare.com
DM_MASTER_PORT=443
DM_CONNECTION_MODE=cloudflare
DM_SECRET_KEY=your-64-character-secret-key
DM_SLAVE_NAME=slave-01
DM_LOG_LEVEL=INFO
```

Secure the configuration file:
```bash
sudo chmod 600 /opt/dm-trafficbot/.env
sudo chown dm-slave:dm-slave /opt/dm-trafficbot/.env
```

### Install Systemd Service

```bash
# Copy service file
sudo cp /opt/dm-trafficbot/deploy/dm-slave.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable dm-slave

# Start the service
sudo systemctl start dm-slave
```

### Service Management Commands

```bash
# Start/stop/restart
sudo systemctl start dm-slave
sudo systemctl stop dm-slave
sudo systemctl restart dm-slave

# Check status
sudo systemctl status dm-slave

# View logs (live)
journalctl -u dm-slave -f

# View recent logs
journalctl -u dm-slave --since "10 minutes ago"

# View logs since boot
journalctl -u dm-slave -b
```

### Running Manually (Testing)

For testing or debugging, run manually:

```bash
cd /opt/dm-trafficbot
source .venv/bin/activate

# With command-line arguments
python slave.py --master 192.168.1.100:8765 --secret "your-key" --name slave-test

# Or source the .env file
source .env && python slave.py --log-level DEBUG
```

---

## 4. Relay Server Setup

The Relay Server enables NAT traversal for both Master and Slaves.

### When to Use

- Master is behind NAT without port forwarding capability
- Multiple networks need to connect
- Want to hide Master's IP from slaves
- Corporate/restricted network environments

### VPS Requirements

- Linux VPS with public IP
- Python 3.10+
- Port 8765 open (or custom)
- Minimal resources: 1 vCPU, 512MB RAM

Providers: DigitalOcean ($4/mo), Vultr ($3.50/mo), AWS Lightsail, etc.

### Automated Installation

```bash
cd /path/to/darkmatter
sudo ./deploy/install-relay.sh
```

### Manual Installation

```bash
# 1. Create service user
sudo useradd -r -s /usr/sbin/nologin -d /opt/dm-relay dm-relay

# 2. Create directory
sudo mkdir -p /opt/dm-relay
sudo chown dm-relay:dm-relay /opt/dm-relay

# 3. Copy files
sudo cp relay.py requirements.txt /opt/dm-relay/
sudo cp -r core/ /opt/dm-relay/
sudo cp -r deploy/ /opt/dm-relay/

# 4. Setup virtual environment
cd /opt/dm-relay
sudo -u dm-relay python3 -m venv .venv
sudo -u dm-relay .venv/bin/pip install -r requirements.txt
```

### Configuration (.env file)

Create `/opt/dm-relay/.env`:

```bash
# Bind to all interfaces
DM_RELAY_HOST=0.0.0.0

# Listen port
DM_RELAY_PORT=8765

# SAME secret key as Master and Slaves
DM_SECRET_KEY=your-64-character-secret-key-here

# Logging level
DM_LOG_LEVEL=INFO
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Install Systemd Service

```bash
sudo cp /opt/dm-relay/deploy/dm-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dm-relay
sudo systemctl start dm-relay
```

### Firewall Configuration

```bash
# UFW (Ubuntu)
sudo ufw allow 8765/tcp

# firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload

# iptables
sudo iptables -A INPUT -p tcp --dport 8765 -j ACCEPT
```

For cloud providers, also configure Security Groups/Firewall Rules in the dashboard.

### Connecting Master to Relay

1. Open DarkMatter GUI → **Master Control**
2. Select **Relay** mode
3. Enter **Relay URL:** `your-vps-ip:8765`
4. Enter the **Secret Key**
5. Click **CONNECT**

### Connecting Slaves to Relay

Configure slave `.env`:
```bash
DM_MASTER_HOST=your-vps-ip
DM_MASTER_PORT=8765
DM_CONNECTION_MODE=relay
DM_SECRET_KEY=same-secret-key
```

---

## 5. Cloudflare Tunnel Setup

Cloudflare Tunnel provides secure access without a VPS or port forwarding.

### When to Use

- No VPS available
- Dynamic home IP address
- Want to hide home IP completely
- Need free DDoS protection
- Quick testing setup

### Prerequisites

1. Cloudflare account (free tier works)
2. `cloudflared` CLI tool installed

### Install cloudflared

**Windows:**
```powershell
winget install Cloudflare.cloudflared
```

**Linux:**
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

### Quick Tunnel (Testing)

For quick testing with a random URL:

```bash
# 1. Start DarkMatter Master (Direct mode, port 8765)

# 2. In separate terminal, create tunnel
cloudflared tunnel --url ws://localhost:8765

# Output:
# Your quick Tunnel has been created! Visit it at:
# https://random-words-here.trycloudflare.com
```

Configure slaves:
```bash
DM_MASTER_HOST=random-words-here.trycloudflare.com
DM_CONNECTION_MODE=cloudflare
```

**Note:** Quick tunnel URLs change on every restart.

### Permanent Tunnel Setup

For a stable URL with your domain:

```bash
# 1. Login to Cloudflare
cloudflared tunnel login

# 2. Create named tunnel
cloudflared tunnel create dm-master
# Note the tunnel ID displayed

# 3. Create DNS record
cloudflared tunnel route dns dm-master dm.yourdomain.com
```

Create config file `~/.cloudflared/config.yml`:
```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: ~/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: dm.yourdomain.com
    service: ws://localhost:8765
  - service: http_status:404
```

Run the tunnel:
```bash
cloudflared tunnel run dm-master
```

### Run as Windows Service

1. Open Task Scheduler
2. Create Basic Task → "DarkMatter Tunnel"
3. Trigger: At log on
4. Action: Start program
5. Program: `cloudflared`
6. Arguments: `tunnel run dm-master`

### Run as Linux Service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

For full details, see [docs/cloudflare-tunnel.md](cloudflare-tunnel.md).

---

## 6. Environment Variables Reference

### Slave Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DM_MASTER_HOST` | **Yes** | - | Master/Relay IP or Cloudflare URL |
| `DM_MASTER_PORT` | No | `8765` | Connection port |
| `DM_SECRET_KEY` | **Yes** | - | Authentication key (min 32 chars) |
| `DM_SLAVE_NAME` | No | `slave-01` | Display name in Master GUI |
| `DM_CONNECTION_MODE` | No | `direct` | `direct`, `relay`, or `cloudflare` |
| `DM_LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Relay Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DM_RELAY_HOST` | No | `0.0.0.0` | Bind address |
| `DM_RELAY_PORT` | No | `8765` | Listen port |
| `DM_SECRET_KEY` | **Yes** | - | Authentication key (min 32 chars) |
| `DM_LOG_LEVEL` | No | `INFO` | Logging level |

---

## 7. Troubleshooting

### Connection Issues

| Problem | Possible Causes | Solution |
|---------|-----------------|----------|
| "Connection refused" | Server not running, wrong port | Verify server is running, check port |
| "Authentication failed" | Secret key mismatch | Copy key exactly, check for spaces |
| "Connection timeout" | Firewall blocking, wrong IP | Test with `nc -zv host port` |
| Slave connects then disconnects | Version mismatch, config error | Check logs: `journalctl -u dm-slave -f` |

### Debug Commands

```bash
# Test network connectivity
nc -zv master-ip 8765
telnet master-ip 8765

# Check if port is listening (on server)
sudo ss -tlnp | grep 8765
sudo netstat -tlnp | grep 8765

# Test WebSocket connection
python3 -c "
import asyncio
import websockets
async def test():
    async with websockets.connect('ws://host:8765') as ws:
        print('Connected!')
asyncio.run(test())
"

# View detailed logs
journalctl -u dm-slave -f --output=verbose
```

### Common Fixes

**Slave won't start:**
```bash
# Check .env file exists and is readable
ls -la /opt/dm-trafficbot/.env

# Test configuration manually
cd /opt/dm-trafficbot
source .env
.venv/bin/python slave.py --log-level DEBUG
```

**Relay not accepting connections:**
```bash
# Check if relay is bound to port
sudo ss -tlnp | grep 8765

# Check firewall
sudo ufw status verbose
sudo iptables -L -n | grep 8765
```

**Master won't start server:**
- Check if port 8765 is already in use
- Verify secret key is at least 32 characters
- Check Windows Firewall allows the port

**Cloudflare tunnel issues:**
```bash
# Check tunnel status
cloudflared tunnel info dm-master

# Ensure Master server is running first
curl http://localhost:8765
```

### Log Locations

| Component | Log Command |
|-----------|-------------|
| Slave | `journalctl -u dm-slave -f` |
| Relay | `journalctl -u dm-relay -f` |
| Master | DarkMatter GUI → Master Control → Activity Log |
| Cloudflare | `journalctl -u cloudflared -f` |

---

## 8. Security Best Practices

### Secret Key Management

1. **Generate strong keys** (64+ character hex strings):
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Never share keys** via chat, email, or version control

3. **Rotate keys periodically**: Update Master GUI, then all slaves

4. **Store securely**:
   - Use `.env` files with `chmod 600`
   - Never commit `.env` files to git

### Network Security

1. **Firewall rules** - Only allow necessary ports:
   ```bash
   # Allow from specific IP only
   sudo ufw allow from 10.0.0.5 to any port 8765
   ```

2. **Use Relay/Cloudflare** to hide Master's IP

3. **VPN** - Additional layer between Master and Relay

4. **TLS** - Cloudflare mode provides automatic TLS

### Service Hardening

The included systemd services have security options:
- `NoNewPrivileges=yes` - Prevent privilege escalation
- `ProtectSystem=strict` - Read-only filesystem
- `ProtectHome=yes` - No access to /home directories
- `PrivateTmp=yes` - Isolated /tmp
- `User=dm-slave` - Non-root execution

### Monitoring

```bash
# Watch for failed authentication
journalctl -u dm-relay -f | grep -i "auth\|fail\|reject"

# Monitor connection counts
watch -n5 'ss -tn state established | grep 8765 | wc -l'

# Check service uptime
systemctl status dm-slave dm-relay
```

### SSH Security (for Linux servers)

```bash
# Disable password authentication
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Use SSH keys only
```

---

## Quick Reference

### Startup Commands

**Direct Mode:**
1. Master: DarkMatter GUI → Master Control → START SERVER
2. Slave: `sudo systemctl start dm-slave`

**Relay Mode:**
1. Relay: `sudo systemctl start dm-relay`
2. Master: Master Control → Relay → CONNECT
3. Slave: `sudo systemctl start dm-slave`

**Cloudflare Mode:**
1. Master: Master Control → Direct → START SERVER
2. Tunnel: `cloudflared tunnel run dm-master`
3. Slave: `sudo systemctl start dm-slave`

### Service Commands

```bash
# Slave
sudo systemctl {start|stop|restart|status} dm-slave
journalctl -u dm-slave -f

# Relay
sudo systemctl {start|stop|restart|status} dm-relay
journalctl -u dm-relay -f
```

### Configuration Files

| Component | Config Location |
|-----------|-----------------|
| Slave | `/opt/dm-trafficbot/.env` |
| Relay | `/opt/dm-relay/.env` |
| Master | `resources/settings.json` (GUI managed) |
| Cloudflare | `~/.cloudflared/config.yml` |
