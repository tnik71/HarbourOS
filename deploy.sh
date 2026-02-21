#!/bin/bash
set -euo pipefail

# HarbourOS Deploy — Push updates to a running Pi
# Usage: ./deploy.sh [hostname]
#   hostname defaults to harbouros.local

PI_HOST="${1:-harbouros.local}"
PI_USER="harbouros"
PI_TARGET="${PI_USER}@${PI_HOST}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  HarbourOS Deploy → ${PI_HOST}"
echo "========================================="

# Verify SSH connectivity
echo ""
echo "Checking SSH connection..."
if ! ssh -o ConnectTimeout=5 "${PI_TARGET}" "echo ok" >/dev/null 2>&1; then
    echo "ERROR: Cannot reach ${PI_HOST} via SSH."
    echo "Make sure the Pi is on and SSH is accessible."
    exit 1
fi
echo "  Connected."

# Step 1: Sync admin UI code
echo ""
echo "[1/4] Syncing admin UI code..."
rsync -avz --delete \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='tests/' \
    --exclude='*.pyc' \
    "${SCRIPT_DIR}/admin-ui/harbouros_admin/" \
    "${PI_TARGET}:/tmp/harbouros-deploy/harbouros_admin/"

rsync -avz \
    "${SCRIPT_DIR}/admin-ui/requirements.txt" \
    "${PI_TARGET}:/tmp/harbouros-deploy/requirements.txt"

# Step 2: Sync config files
echo ""
echo "[2/4] Syncing config files..."
rsync -avz \
    "${SCRIPT_DIR}/config/" \
    "${PI_TARGET}:/tmp/harbouros-deploy/config/"

# Step 3: Sync the apply script
echo ""
echo "[3/4] Syncing apply script..."
rsync -avz \
    "${SCRIPT_DIR}/scripts/apply-update.sh" \
    "${PI_TARGET}:/tmp/harbouros-deploy/apply-update.sh"
ssh "${PI_TARGET}" "chmod +x /tmp/harbouros-deploy/apply-update.sh"

# Step 4: Apply on Pi
echo ""
echo "[4/4] Applying update on Pi..."
ssh -t "${PI_TARGET}" "sudo /tmp/harbouros-deploy/apply-update.sh"

echo ""
echo "========================================="
echo "  Deploy complete!"
echo "========================================="
