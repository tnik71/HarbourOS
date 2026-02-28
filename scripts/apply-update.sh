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
NEED_SYSCTL_RELOAD=0

# --- One-time migrations (v1.0.2: install fail2ban, logrotate, SSH hardening) ---
MIGRATION_FLAG="/etc/harbouros/.migration-1.0.2"
if [ ! -f "${MIGRATION_FLAG}" ]; then
    echo "  Running v1.0.2 migration..."

    # Install fail2ban and logrotate if missing
    for pkg in fail2ban logrotate; do
        if ! dpkg -l "$pkg" >/dev/null 2>&1; then
            echo "  Installing ${pkg}..."
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg"
        fi
    done

    # SSH X11Forwarding hardening
    if grep -q "^X11Forwarding yes" /etc/ssh/sshd_config 2>/dev/null; then
        sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config
        echo "  Disabled SSH X11Forwarding"
    elif grep -q "^#X11Forwarding" /etc/ssh/sshd_config 2>/dev/null; then
        sed -i 's/^#X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config
        echo "  Disabled SSH X11Forwarding"
    fi

    # Enable fail2ban
    systemctl enable fail2ban.service 2>/dev/null || true
    systemctl start fail2ban.service 2>/dev/null || true

    mkdir -p "$(dirname "${MIGRATION_FLAG}")"
    touch "${MIGRATION_FLAG}"
    echo "  v1.0.2 migration complete."
fi

# --- One-time migration (v1.0.5: run as non-root harbouros user) ---
MIGRATION_105="/etc/harbouros/.migration-1.0.5"
if [ ! -f "${MIGRATION_105}" ]; then
    echo "  Running v1.0.5 migration (non-root service user)..."

    # Create harbouros system user if missing
    if ! id -u harbouros >/dev/null 2>&1; then
        useradd --system --no-create-home --shell /usr/sbin/nologin harbouros
        echo "  Created harbouros system user."
    fi

    # Set ownership on config and app dirs
    chown -R harbouros:harbouros /etc/harbouros
    chown -R harbouros:harbouros /opt/harbouros

    # Install sudoers file
    if [ -f "${STAGING}/config/harbouros-sudoers" ]; then
        install -m 400 "${STAGING}/config/harbouros-sudoers" /etc/sudoers.d/harbouros
        echo "  Installed sudoers file."
    fi

    touch "${MIGRATION_105}"
    NEED_RESTART=1
    echo "  v1.0.5 migration complete."
fi

# --- Sudoers file (update on every deploy) ---
if [ -f "${STAGING}/config/harbouros-sudoers" ]; then
    if ! diff -q "${STAGING}/config/harbouros-sudoers" "/etc/sudoers.d/harbouros" >/dev/null 2>&1; then
        echo "  Updating sudoers file..."
        install -m 400 "${STAGING}/config/harbouros-sudoers" /etc/sudoers.d/harbouros
    fi
fi

# --- Admin UI code ---
if [ -d "${STAGING}/harbouros_admin" ]; then
    echo "  Updating admin UI code..."
    rm -rf "${ADMIN_DIR}/harbouros_admin"
    cp -r "${STAGING}/harbouros_admin" "${ADMIN_DIR}/harbouros_admin"
    chown -R harbouros:harbouros "${ADMIN_DIR}/harbouros_admin"
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

# --- Sysctl hardening ---
if [ -f "${STAGING}/config/sysctl-hardening.conf" ]; then
    if ! diff -q "${STAGING}/config/sysctl-hardening.conf" "/etc/sysctl.d/99-harbouros.conf" >/dev/null 2>&1; then
        echo "  Updating sysctl hardening..."
        cp "${STAGING}/config/sysctl-hardening.conf" "/etc/sysctl.d/99-harbouros.conf"
        NEED_SYSCTL_RELOAD=1
    fi
fi

# --- fail2ban config ---
if [ -f "${STAGING}/config/fail2ban-sshd.conf" ]; then
    mkdir -p /etc/fail2ban/jail.d
    if ! diff -q "${STAGING}/config/fail2ban-sshd.conf" "/etc/fail2ban/jail.d/sshd.conf" >/dev/null 2>&1; then
        echo "  Updating fail2ban SSH jail config..."
        cp "${STAGING}/config/fail2ban-sshd.conf" "/etc/fail2ban/jail.d/sshd.conf"
        systemctl restart fail2ban.service 2>/dev/null || true
    fi
fi

# --- Plex logrotate config ---
if [ -f "${STAGING}/config/logrotate-plex.conf" ]; then
    if ! diff -q "${STAGING}/config/logrotate-plex.conf" "/etc/logrotate.d/plex" >/dev/null 2>&1; then
        echo "  Updating Plex logrotate config..."
        cp "${STAGING}/config/logrotate-plex.conf" "/etc/logrotate.d/plex"
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
