#!/bin/bash
# DarkMatter Traffic Bot - Linux Slave Installer
# For Debian/Ubuntu systems
#
# Usage: sudo ./install.sh
#
# This script:
# 1. Installs system dependencies
# 2. Creates dm-slave user
# 3. Sets up /opt/dm-trafficbot
# 4. Creates Python venv and installs requirements
# 5. Creates .env template
# 6. Installs and enables systemd service

set -e

# --- Configuration ---
INSTALL_DIR="/opt/dm-trafficbot"
SERVICE_USER="dm-slave"
SERVICE_GROUP="dm-slave"
VENV_PATH="${INSTALL_DIR}/.venv"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Check root ---
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root. Use: sudo ./install.sh"
    fi
}

# --- Install dependencies ---
install_deps() {
    log_info "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y python3 python3-venv python3-pip git curl >/dev/null
    log_success "Dependencies installed"
}

# --- Create service user ---
create_user() {
    log_info "Creating service user '${SERVICE_USER}'..."
    if ! id -u "${SERVICE_USER}" &>/dev/null; then
        useradd -r -s /usr/sbin/nologin -d "${INSTALL_DIR}" -m "${SERVICE_USER}"
        log_success "User ${SERVICE_USER} created"
    else
        log_warn "User ${SERVICE_USER} already exists"
    fi
}

# --- Setup install directory ---
setup_directory() {
    log_info "Setting up ${INSTALL_DIR}..."
    mkdir -p "${INSTALL_DIR}"
    
    # Copy project files (assumes script is run from project root)
    if [ -f "slave.py" ]; then
        cp -r core/ "${INSTALL_DIR}/"
        cp slave.py requirements.txt "${INSTALL_DIR}/"
        cp -r deploy/ "${INSTALL_DIR}/"
        mkdir -p "${INSTALL_DIR}/resources"
        log_success "Project files copied"
    else
        log_error "slave.py not found. Run this script from the project root."
    fi
    
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"
}

# --- Setup Python venv ---
setup_venv() {
    log_info "Setting up Python virtual environment..."
    if [ ! -d "${VENV_PATH}" ]; then
        python3 -m venv "${VENV_PATH}"
    fi
    
    "${VENV_PATH}/bin/pip" install --upgrade pip -q
    "${VENV_PATH}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q
    
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${VENV_PATH}"
    log_success "Virtual environment ready"
}

# --- Create .env file ---
create_env() {
    log_info "Creating .env configuration file..."
    ENV_FILE="${INSTALL_DIR}/.env"
    
    if [ ! -f "${ENV_FILE}" ]; then
        cat > "${ENV_FILE}" << 'EOF'
# DarkMatter Traffic Bot Slave Configuration
# Edit these values to connect to your master server

DM_MASTER_HOST=192.168.1.100
DM_MASTER_PORT=8765
DM_SECRET_KEY=your-32-character-or-longer-secret-key-here
DM_SLAVE_NAME=slave-$(hostname)
EOF
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
        log_success ".env created (edit with your settings)"
    else
        log_warn ".env already exists, skipping"
    fi
}

# --- Install systemd service ---
install_service() {
    log_info "Installing systemd service..."
    cp "${INSTALL_DIR}/deploy/dm-slave.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable dm-slave
    log_success "Service installed and enabled"
}

# --- Main ---
main() {
    echo "=============================================="
    echo "  DarkMatter Traffic Bot - Slave Installer"
    echo "=============================================="
    echo ""
    
    check_root
    install_deps
    create_user
    setup_directory
    setup_venv
    create_env
    install_service
    
    echo ""
    echo -e "${GREEN}Installation complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit configuration:  sudo nano ${INSTALL_DIR}/.env"
    echo "  2. Start service:       sudo systemctl start dm-slave"
    echo "  3. Check status:        sudo systemctl status dm-slave"
    echo "  4. View logs:           journalctl -u dm-slave -f"
    echo ""
}

main "$@"
