#!/bin/bash
set -euo pipefail

# HarbourOS Uninstall — Reverses remote-install.sh changes
# Leaves CasaOS, Docker, and existing services intact
# Usage: Run on the Pi as root

echo "========================================="
echo "  HarbourOS Uninstall"
echo "========================================="
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root."
    exit 1
fi

# =============================================
# 1. Stop and remove HarbourOS services
# =============================================
echo "[1/8] Stopping HarbourOS services..."

for unit in harbouros.service harbouros-firstboot.service harbouros-plex-update.timer harbouros-plex-update.service; do
    if systemctl is-enabled "$unit" 2>/dev/null | grep -q "enabled"; then
        echo "  Disabling $unit"
        systemctl disable --now "$unit" 2>/dev/null || true
    else
        echo "  $unit not enabled, skipping"
    fi
done

# Remove HarbourOS systemd unit files
echo "  Removing HarbourOS systemd units..."
rm -f /etc/systemd/system/harbouros.service
rm -f /etc/systemd/system/harbouros-firstboot.service
rm -f /etc/systemd/system/harbouros-plex-update.service
rm -f /etc/systemd/system/harbouros-plex-update.timer

# Remove Plex systemd override (LimitNOFILE) — only the HarbourOS override
if [ -f /etc/systemd/system/plexmediaserver.service.d/override.conf ]; then
    echo "  Removing Plex systemd override..."
    rm -f /etc/systemd/system/plexmediaserver.service.d/override.conf
    rmdir /etc/systemd/system/plexmediaserver.service.d 2>/dev/null || true
fi

# Disable systemd plexmediaserver if HarbourOS enabled it (Docker Plex is separate)
if systemctl is-enabled plexmediaserver.service 2>/dev/null | grep -q "enabled"; then
    echo "  Disabling systemd plexmediaserver (Docker Plex is unaffected)..."
    systemctl disable --now plexmediaserver.service 2>/dev/null || true
fi

# Remove any NAS mount/automount units HarbourOS created
echo "  Removing HarbourOS NAS mount units..."
for f in /etc/systemd/system/media-nas-*.mount /etc/systemd/system/media-nas-*.automount; do
    if [ -f "$f" ]; then
        unit_name=$(basename "$f")
        systemctl disable --now "$unit_name" 2>/dev/null || true
        rm -f "$f"
        echo "    Removed $unit_name"
    fi
done

systemctl daemon-reload

# =============================================
# 2. Remove HarbourOS application files
# =============================================
echo ""
echo "[2/8] Removing HarbourOS application files..."

rm -rf /opt/harbouros
echo "  Removed /opt/harbouros/"

rm -f /usr/local/bin/harbouros-plex-update.sh
echo "  Removed Plex update script"

# =============================================
# 3. Remove HarbourOS config (but NOT user data like NAS content)
# =============================================
echo ""
echo "[3/8] Removing HarbourOS configuration..."

rm -rf /etc/harbouros
echo "  Removed /etc/harbouros/"

# Remove HarbourOS avahi service
rm -f /etc/avahi/services/harbouros.service
echo "  Removed avahi HarbourOS service"

# =============================================
# 4. Restore sysctl settings
# =============================================
echo ""
echo "[4/8] Restoring sysctl settings..."

if [ -f /etc/sysctl.d/99-harbouros.conf ]; then
    rm -f /etc/sysctl.d/99-harbouros.conf
    sysctl --system >/dev/null 2>&1
    echo "  Removed HarbourOS sysctl hardening"
else
    echo "  No HarbourOS sysctl config found, skipping"
fi

# =============================================
# 5. Remove fail2ban config
# =============================================
echo ""
echo "[5/8] Removing fail2ban config..."

if [ -f /etc/fail2ban/jail.d/sshd.conf ]; then
    rm -f /etc/fail2ban/jail.d/sshd.conf
    systemctl restart fail2ban.service 2>/dev/null || true
    echo "  Removed HarbourOS fail2ban SSH jail"
else
    echo "  No HarbourOS fail2ban config found, skipping"
fi

# =============================================
# 6. Remove Plex logrotate config
# =============================================
echo ""
echo "[6/8] Removing Plex logrotate config..."

if [ -f /etc/logrotate.d/plex ]; then
    rm -f /etc/logrotate.d/plex
    echo "  Removed Plex logrotate config"
else
    echo "  No Plex logrotate config found, skipping"
fi

# =============================================
# 7. Restore hostname and SSH settings
# =============================================
echo ""
echo "[7/8] Restoring system settings..."

# Restore hostname if it was changed to harbouros
CURRENT_HOSTNAME=$(hostname)
if [ "$CURRENT_HOSTNAME" = "harbouros" ]; then
    # Try to find original hostname from /etc/hosts
    OLD_HOSTNAME=$(grep "127.0.1.1" /etc/hosts | awk '{print $NF}')
    if [ -n "$OLD_HOSTNAME" ] && [ "$OLD_HOSTNAME" != "harbouros" ]; then
        echo "$OLD_HOSTNAME" > /etc/hostname
        sed -i "s/127.0.1.1.*/127.0.1.1\t${OLD_HOSTNAME}/" /etc/hosts
        echo "  Hostname restored to: $OLD_HOSTNAME (takes effect on reboot)"
    else
        echo "  WARNING: Could not determine original hostname."
        echo "  Current hostname is 'harbouros'. You may want to change it manually:"
        echo "    sudo hostnamectl set-hostname <your-hostname>"
    fi
else
    echo "  Hostname is '$CURRENT_HOSTNAME' (not 'harbouros'), no change needed"
fi

# Restore SSH root login (undo the hardening)
if grep -q "^PermitRootLogin no" /etc/ssh/sshd_config; then
    sed -i 's/^PermitRootLogin no/#PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    echo "  SSH root login restored to default"
fi

# Restore SSH X11Forwarding
if grep -q "^X11Forwarding no" /etc/ssh/sshd_config; then
    sed -i 's/^X11Forwarding no/#X11Forwarding yes/' /etc/ssh/sshd_config
    echo "  SSH X11Forwarding restored to default"
fi

# Re-enable services that HarbourOS disabled
for svc in bluetooth.service triggerhappy.service apt-daily-upgrade.timer apt-daily.timer; do
    if systemctl list-unit-files "$svc" >/dev/null 2>&1; then
        systemctl enable "$svc" 2>/dev/null || true
        echo "  Re-enabled $svc"
    fi
done

# =============================================
# 8. Restore boot config
# =============================================
echo ""
echo "[8/8] Restoring boot configuration..."

# Remove HarbourOS boot tweaks from config.txt
if [ -f /boot/firmware/config.txt ]; then
    if grep -q "gpu_mem=16" /boot/firmware/config.txt; then
        sed -i '/^gpu_mem=16$/d' /boot/firmware/config.txt
        echo "  Removed gpu_mem=16 from config.txt"
    fi
    if grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt; then
        sed -i '/^dtoverlay=disable-bt$/d' /boot/firmware/config.txt
        echo "  Removed dtoverlay=disable-bt from config.txt"
    fi
fi

# Remove quiet boot from cmdline.txt
if [ -f /boot/firmware/cmdline.txt ]; then
    if grep -q "quiet loglevel=3" /boot/firmware/cmdline.txt; then
        sed -i 's/ quiet loglevel=3//' /boot/firmware/cmdline.txt
        echo "  Removed quiet boot from cmdline.txt"
    fi
fi

# =============================================
# Cleanup
# =============================================
echo ""
echo "  Removing NAS mount points (if empty)..."
if [ -d /media/nas ]; then
    # Unmount anything still mounted
    for mp in /media/nas/*/; do
        if mountpoint -q "$mp" 2>/dev/null; then
            umount -l "$mp" 2>/dev/null || true
        fi
    done
    rm -rf /media/nas
    echo "  Removed /media/nas/"
fi

# Remove leftover staging directory
rm -rf /tmp/harbouros-install

# Reload everything
systemctl daemon-reload

echo ""
echo "========================================="
echo "  HarbourOS has been removed."
echo ""
echo "  What was kept:"
echo "    - CasaOS and all Docker containers"
echo "    - System packages (nfs-common, cifs-utils, etc.)"
echo "    - Your SSH keys and user account"
echo ""
echo "  Reboot recommended: sudo reboot"
echo "========================================="
