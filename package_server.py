#!/usr/bin/env python3
"""
Package server deployment files into server_deploy.zip

Creates a minimal deployment package for Linux slave and relay servers.
Only includes files necessary for headless slave/relay operation.

Usage:
    python package_server.py

Output:
    server_deploy.zip (~60KB) containing:
    - slave.py (slave agent entry point)
    - relay.py (relay server entry point)
    - requirements.txt
    - core/ (essential modules only)
    - deploy/ (systemd services, install scripts)
    - docs/ (Cloudflare Tunnel setup guide)
    - resources/ (empty directory structure)
"""

import os
import zipfile
from pathlib import Path
from datetime import datetime

# Project root
PROJECT_ROOT = Path(__file__).parent

# Output zip file
OUTPUT_ZIP = PROJECT_ROOT / "server_deploy.zip"

# Files to include (relative to project root)
INCLUDE_FILES = [
    "slave.py",
    "relay.py",
    "requirements.txt",
]

# Directories to include completely
INCLUDE_DIRS = [
    "deploy",
    "docs",
]

# Core modules required for slave/relay operation
CORE_MODULES = [
    "__init__.py",
    "models.py",
    "constants.py",
    "websocket_server.py",
    "websocket_client.py",  # WebSocket client for slave connections
    "slave_controller.py",
    "relay_server.py",      # Relay server for NAT traversal
    "relay_client.py",      # Relay client for Controller
    "scanner.py",
    "proxy_manager.py",
    "engine.py",
    "validators.py",
    "header_manager.py",
    "captcha_manager.py",   # For traffic operations
    "captcha_solver.py",    # Legacy captcha support
]

# Empty directories to create in zip
EMPTY_DIRS = [
    "resources",
]

# Files/patterns to always exclude
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
    ".venv",
    "*.egg-info",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
]


def should_exclude(path: Path) -> bool:
    """Check if path matches any exclude pattern."""
    path_str = str(path)
    name = path.name

    for pattern in EXCLUDE_PATTERNS:
        if pattern.startswith("*"):
            # Extension pattern
            if name.endswith(pattern[1:]):
                return True
        elif pattern in path_str or name == pattern:
            return True

    return False


def package_server_files():
    """Create server_deploy.zip with minimal slave files."""

    print("=" * 50)
    print("  DarkMatter Traffic Bot - Server Packager")
    print("=" * 50)
    print()

    files_added = []
    total_size = 0

    # Remove existing zip if present
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
        print(f"[INFO] Removed existing {OUTPUT_ZIP.name}")

    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zf:

        # 1. Add individual files
        print("\n[1/4] Adding root files...")
        for filename in INCLUDE_FILES:
            filepath = PROJECT_ROOT / filename
            if filepath.exists():
                zf.write(filepath, filename)
                size = filepath.stat().st_size
                total_size += size
                files_added.append((filename, size))
                print(f"  + {filename} ({size:,} bytes)")
            else:
                print(f"  ! {filename} NOT FOUND - skipping")

        # 2. Add core modules (selective)
        print("\n[2/4] Adding core modules...")
        core_dir = PROJECT_ROOT / "core"
        for module in CORE_MODULES:
            filepath = core_dir / module
            arcname = f"core/{module}"
            if filepath.exists():
                zf.write(filepath, arcname)
                size = filepath.stat().st_size
                total_size += size
                files_added.append((arcname, size))
                print(f"  + core/{module} ({size:,} bytes)")
            else:
                print(f"  ! core/{module} NOT FOUND - skipping")

        # 3. Add complete directories (deploy/, docs/)
        print("\n[3/4] Adding deploy and docs directories...")
        for dirname in INCLUDE_DIRS:
            dir_path = PROJECT_ROOT / dirname
            if dir_path.exists() and dir_path.is_dir():
                for filepath in dir_path.rglob("*"):
                    if filepath.is_file() and not should_exclude(filepath):
                        arcname = str(filepath.relative_to(PROJECT_ROOT))
                        zf.write(filepath, arcname)
                        size = filepath.stat().st_size
                        total_size += size
                        files_added.append((arcname, size))
                        print(f"  + {arcname} ({size:,} bytes)")

        # 4. Create empty directories
        print("\n[4/4] Creating empty directories...")
        for dirname in EMPTY_DIRS:
            # ZipFile needs a trailing slash for directories
            zf.writestr(f"{dirname}/", "")
            print(f"  + {dirname}/ (empty)")

    # Summary
    zip_size = OUTPUT_ZIP.stat().st_size

    print("\n" + "=" * 50)
    print("  Package Complete!")
    print("=" * 50)
    print(f"\n  Output: {OUTPUT_ZIP.name}")
    print(f"  Files:  {len(files_added)}")
    print(f"  Size:   {zip_size:,} bytes ({zip_size / 1024:.1f} KB)")
    print(f"  Ratio:  {(1 - zip_size / total_size) * 100:.1f}% compression")

    print("\n  Deployment options:")
    print()
    print("  [A] SLAVE AGENT:")
    print("    1. Copy server_deploy.zip to Linux server")
    print("    2. unzip server_deploy.zip -d /tmp/dm-trafficbot")
    print("    3. cd /tmp/dm-trafficbot && sudo bash deploy/install.sh")
    print("    4. sudo nano /opt/dm-trafficbot/.env  # Configure master connection")
    print("    5. sudo systemctl start dm-slave")
    print()
    print("  [B] RELAY SERVER (for NAT traversal):")
    print("    1. Copy server_deploy.zip to VPS")
    print("    2. unzip server_deploy.zip -d /tmp/dm-relay")
    print("    3. cd /tmp/dm-relay && sudo bash deploy/install-relay.sh")
    print("    4. sudo nano /opt/dm-relay/.env  # Set DM_SECRET_KEY")
    print("    5. sudo systemctl start dm-relay")
    print()
    print("  [C] CLOUDFLARE TUNNEL:")
    print("    See docs/cloudflare-tunnel.md for setup instructions")
    print()

    return OUTPUT_ZIP


if __name__ == "__main__":
    package_server_files()
