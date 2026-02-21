#!/bin/bash
set -euo pipefail

# HarbourOS Remote Install — Push and install HarbourOS on a Pi over SSH
# Usage: ./install-remote.sh <hostname-or-ip>
#   Example: ./install-remote.sh 192.168.1.50
#   Example: ./install-remote.sh harbouros.local

PI_HOST="${1:-}"
if [ -z "$PI_HOST" ]; then
    echo "Usage: $0 <hostname-or-ip>"
    echo "  Example: $0 192.168.1.50"
    exit 1
fi

# SSH user: override with PI_USER env var, or auto-detect
PI_USER="${PI_USER:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  HarbourOS Remote Install → ${PI_HOST}"
echo "========================================="

# --- Detect SSH user ---
if [ -z "$PI_USER" ]; then
    echo ""
    echo "Detecting SSH user..."
    for user in tnik71 pi harbouros admin; do
        if ssh -o ConnectTimeout=5 -o BatchMode=yes "${user}@${PI_HOST}" "echo ok" >/dev/null 2>&1; then
            PI_USER="$user"
            break
        fi
    done
fi

if [ -z "$PI_USER" ]; then
    echo "ERROR: Cannot connect via SSH. Tried users: tnik71, pi, harbouros, admin"
    echo "Make sure:"
    echo "  1. The Pi is on and reachable at ${PI_HOST}"
    echo "  2. SSH is enabled"
    echo "  3. You have SSH key access set up (run: ssh-copy-id <user>@${PI_HOST})"
    echo ""
    echo "Or specify the user: PI_USER=myuser make install-remote PI=${PI_HOST}"
    exit 1
fi

PI_TARGET="${PI_USER}@${PI_HOST}"
echo "  Connected as ${PI_TARGET}"

# --- Verify it's a Raspberry Pi ---
echo ""
echo "Checking target system..."
ARCH=$(ssh "${PI_TARGET}" "dpkg --print-architecture 2>/dev/null || uname -m")
echo "  Architecture: ${ARCH}"

# --- Confirm ---
echo ""
echo "This will install HarbourOS on ${PI_HOST}:"
echo "  - Plex Media Server"
echo "  - HarbourOS Admin UI (port 8080)"
echo "  - Firewall rules (nftables)"
echo "  - Security hardening"
echo "  - Hostname → harbouros"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# --- Stage 1: Upload files ---
echo ""
echo "[1/3] Uploading HarbourOS files..."

# Create staging directory on Pi
ssh "${PI_TARGET}" "mkdir -p /tmp/harbouros-install"

# Admin UI code
rsync -avz --delete \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='tests/' \
    --exclude='*.pyc' \
    "${SCRIPT_DIR}/admin-ui/harbouros_admin/" \
    "${PI_TARGET}:/tmp/harbouros-install/harbouros_admin/"

# Requirements
rsync -avz \
    "${SCRIPT_DIR}/admin-ui/requirements.txt" \
    "${PI_TARGET}:/tmp/harbouros-install/requirements.txt"

# Config files
rsync -avz \
    "${SCRIPT_DIR}/config/" \
    "${PI_TARGET}:/tmp/harbouros-install/config/"

# Install script
rsync -avz \
    "${SCRIPT_DIR}/scripts/remote-install.sh" \
    "${PI_TARGET}:/tmp/harbouros-install/remote-install.sh"

ssh "${PI_TARGET}" "chmod +x /tmp/harbouros-install/remote-install.sh"

# --- Stage 2: Run install ---
echo ""
echo "[2/3] Running install on Pi (this may take a few minutes)..."
ssh -t "${PI_TARGET}" "sudo /tmp/harbouros-install/remote-install.sh"

# --- Stage 3: Verify ---
echo ""
echo "[3/3] Verifying installation..."
sleep 3

if ssh "${PI_TARGET}" "systemctl is-active --quiet harbouros.service" 2>/dev/null; then
    echo "  harbouros: running"
else
    echo "  harbouros: NOT running (check logs on Pi)"
fi

if ssh "${PI_TARGET}" "systemctl is-active --quiet plexmediaserver.service" 2>/dev/null; then
    echo "  plexmediaserver: running"
else
    echo "  plexmediaserver: NOT running (may take a moment to start)"
fi

echo ""
echo "========================================="
echo "  HarbourOS install complete!"
echo ""
echo "  Admin UI:  http://${PI_HOST}:8080"
echo "  Plex:      http://${PI_HOST}:32400/web"
echo "  Password:  harbouros"
echo ""
echo "  A reboot is recommended: ssh ${PI_TARGET} sudo reboot"
echo "========================================="
