#!/bin/bash
# DarkMatter Traffic Bot - Linux Slave Uninstaller
#
# Usage: sudo ./uninstall.sh
#
# This script:
# 1. Stops and disables the service
# 2. Removes systemd service file
# 3. Optionally removes user and installation directory

set -e

INSTALL_DIR="/opt/dm-trafficbot"
SERVICE_USER="dm-slave"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} This script must be run as root."
    exit 1
fi

echo "=============================================="
echo "  DarkMatter Traffic Bot - Slave Uninstaller"
echo "=============================================="
echo ""

# Stop and disable service
log_info "Stopping dm-slave service..."
systemctl stop dm-slave 2>/dev/null || true
systemctl disable dm-slave 2>/dev/null || true
log_success "Service stopped"

# Remove service file
log_info "Removing systemd service file..."
rm -f /etc/systemd/system/dm-slave.service
systemctl daemon-reload
log_success "Service file removed"

# Ask about removing installation directory
echo ""
read -p "Remove installation directory ${INSTALL_DIR}? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "${INSTALL_DIR}"
    log_success "Installation directory removed"
else
    log_warn "Installation directory preserved"
fi

# Ask about removing user
read -p "Remove service user ${SERVICE_USER}? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    userdel "${SERVICE_USER}" 2>/dev/null || true
    log_success "User removed"
else
    log_warn "User preserved"
fi

echo ""
echo -e "${GREEN}Uninstallation complete!${NC}"
