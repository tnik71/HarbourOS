#!/bin/bash
set -euo pipefail

# HarbourOS Apply Update — Runs on the Pi as root
# Called by deploy.sh via SSH

STAGING="/tmp/harbouros-deploy"
ADMIN_DIR="/opt/harbouros"
VENV="${ADMIN_DIR}/venv"

echo "HarbourOS: Applying update..."

NEED_RESTART=0
NEED_DAEMON_RELOAD=0
NEED_NFTABLES_RELOAD=0
NEED_SYSCTL_RELOAD=0

# --- Admin UI code ---
if [ -d "${STAGING}/harbouros_admin" ]; then
    echo "  Updating admin UI code..."
    rm -rf "${ADMIN_DIR}/harbouros_admin"
    cp -r "${STAGING}/harbouros_admin" "${ADMIN_DIR}/harbouros_admin"
    NEED_RESTART=1
fi

# --- Python dependencies ---
if [ -f "${STAGING}/requirements.txt" ]; then
    if ! diff -q "${STAGING}/requirements.txt" "${ADMIN_DIR}/requirements.txt" >/dev/null 2>&1; then
        echo "  Installing updated Python dependencies..."
        cp "${STAGING}/requirements.txt" "${ADMIN_DIR}/requirements.txt"
        "${VENV}/bin/pip" install --no-cache-dir -r "${ADMIN_DIR}/requirements.txt"
    else
        echo "  requirements.txt unchanged, skipping pip install."
    fi
fi

# --- Systemd units ---
for unit in harbouros.service harbouros-plex-update.service harbouros-plex-update.timer harbouros-self-update.service harbouros-self-update.timer harbouros-firstboot.service; do
    if [ -f "${STAGING}/config/${unit}" ]; then
        if ! diff -q "${STAGING}/config/${unit}" "/etc/systemd/system/${unit}" >/dev/null 2>&1; then
            echo "  Updating ${unit}..."
            cp "${STAGING}/config/${unit}" "/etc/systemd/system/${unit}"
            NEED_DAEMON_RELOAD=1
        fi
    fi
done

# --- Plex update script ---
if [ -f "${STAGING}/config/harbouros-plex-update.sh" ]; then
    if ! diff -q "${STAGING}/config/harbouros-plex-update.sh" "/usr/local/bin/harbouros-plex-update.sh" >/dev/null 2>&1; then
        echo "  Updating harbouros-plex-update.sh..."
        install -m 755 "${STAGING}/config/harbouros-plex-update.sh" "/usr/local/bin/harbouros-plex-update.sh"
    fi
fi

# --- Self-update script ---
if [ -f "${STAGING}/config/harbouros-self-update.sh" ]; then
    if ! diff -q "${STAGING}/config/harbouros-self-update.sh" "/usr/local/bin/harbouros-self-update.sh" >/dev/null 2>&1; then
        echo "  Updating harbouros-self-update.sh..."
        install -m 755 "${STAGING}/config/harbouros-self-update.sh" "/usr/local/bin/harbouros-self-update.sh"
    fi
fi

# --- Firewall ---
if [ -f "${STAGING}/config/nftables.conf" ]; then
    if ! diff -q "${STAGING}/config/nftables.conf" "/etc/nftables.conf" >/dev/null 2>&1; then
        echo "  Updating nftables.conf..."
        cp "${STAGING}/config/nftables.conf" "/etc/nftables.conf"
        NEED_NFTABLES_RELOAD=1
    fi
fi

# --- Sysctl hardening ---
if [ -f "${STAGING}/config/sysctl-hardening.conf" ]; then
    if ! diff -q "${STAGING}/config/sysctl-hardening.conf" "/etc/sysctl.d/99-harbouros.conf" >/dev/null 2>&1; then
        echo "  Updating sysctl hardening..."
        cp "${STAGING}/config/sysctl-hardening.conf" "/etc/sysctl.d/99-harbouros.conf"
        NEED_SYSCTL_RELOAD=1
    fi
fi

# --- Avahi service ---
if [ -f "${STAGING}/config/avahi/harbouros.service" ]; then
    if ! diff -q "${STAGING}/config/avahi/harbouros.service" "/etc/avahi/services/harbouros.service" >/dev/null 2>&1; then
        echo "  Updating Avahi service..."
        cp "${STAGING}/config/avahi/harbouros.service" "/etc/avahi/services/harbouros.service"
    fi
fi

# --- Reload / Restart ---
if [ "${NEED_DAEMON_RELOAD}" -eq 1 ]; then
    echo "  Reloading systemd daemon..."
    systemctl daemon-reload
fi

if [ "${NEED_NFTABLES_RELOAD}" -eq 1 ]; then
    echo "  Reloading firewall rules..."
    systemctl restart nftables.service
fi

if [ "${NEED_SYSCTL_RELOAD}" -eq 1 ]; then
    echo "  Applying sysctl changes..."
    sysctl --system >/dev/null
fi

if [ "${NEED_RESTART}" -eq 1 ]; then
    echo "  Restarting harbouros service..."
    systemctl restart harbouros.service
    sleep 2
    if systemctl is-active --quiet harbouros.service; then
        echo "  harbouros is running."
    else
        echo "  WARNING: harbouros failed to start!"
        systemctl status harbouros.service --no-pager || true
        exit 1
    fi
fi

# --- Cleanup ---
echo "  Cleaning up staging directory..."
rm -rf "${STAGING}"

echo "HarbourOS: Update applied successfully."
