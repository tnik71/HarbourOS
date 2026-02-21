#!/bin/bash
set -euo pipefail

# HarbourOS Remote Install — Runs on the Pi as root
# Installs HarbourOS onto a running Raspberry Pi OS over SSH
# Usage: Pushed and executed by install-remote.sh from the laptop

STAGING="/tmp/harbouros-install"

echo "========================================="
echo "  HarbourOS Remote Install"
echo "========================================="
echo ""

# --- Sanity checks ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root."
    exit 1
fi

if [ ! -d "${STAGING}/harbouros_admin" ]; then
    echo "ERROR: Staging directory not found at ${STAGING}/harbouros_admin"
    exit 1
fi

ARCH=$(dpkg --print-architecture)
if [ "$ARCH" != "arm64" ]; then
    echo "WARNING: Architecture is ${ARCH}, not arm64. Plex may not install correctly."
fi

# =============================================
# Stage 0: Install system packages
# =============================================
echo "[1/7] Installing system packages..."

# Non-interactive mode: keep existing config files, don't prompt
export DEBIAN_FRONTEND=noninteractive
APT_OPTS="-o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef"

# Fix any broken packages from previous runs
dpkg --configure -a --force-confold 2>/dev/null || true

# Remove any stale Plex apt repo (has SHA-1 signing issues)
rm -f /etc/apt/sources.list.d/plexmediaserver.list
rm -f /usr/share/keyrings/plex-archive-keyring.gpg

apt-get update -qq
apt-get install -y -qq ${APT_OPTS} \
    nfs-common \
    cifs-utils \
    avahi-daemon \
    avahi-utils \
    python3 \
    python3-venv \
    python3-pip \
    nftables \
    curl

# =============================================
# Stage 1: Install Plex Media Server
# =============================================
echo ""
echo "[2/7] Installing Plex Media Server..."

PLEX_ALREADY_RUNNING=0
if ss -tlnp | grep -q ':32400 '; then
    echo "  Plex is already running on port 32400 (managed externally)."
    echo "  Skipping Plex install — will use existing Plex instance."
    PLEX_ALREADY_RUNNING=1
elif ! dpkg -l plexmediaserver >/dev/null 2>&1; then
    echo "  Downloading latest Plex .deb for arm64..."
    PLEX_DEB="/tmp/plexmediaserver.deb"
    # Get the latest Plex download URL for ARM64 Debian
    PLEX_URL=$(curl -fsSL 'https://plex.tv/api/downloads/5.json' | \
        python3 -c "import sys,json; d=json.load(sys.stdin); releases=d['computer']['Linux']['releases']; deb=[r for r in releases if r.get('distro')=='debian' and 'arm64' in r.get('url','')]; print(deb[0]['url'] if deb else '')")
    if [ -z "$PLEX_URL" ]; then
        echo "  ERROR: Could not find Plex ARM64 download URL."
        echo "  Trying fallback: apt repo with trusted=yes..."
        echo "deb [trusted=yes] https://downloads.plex.tv/repo/deb public main" > /etc/apt/sources.list.d/plexmediaserver.list
        apt-get update -qq
        apt-get install -y ${APT_OPTS} plexmediaserver
    else
        echo "  URL: ${PLEX_URL}"
        curl -fSL -o "${PLEX_DEB}" "${PLEX_URL}"
        dpkg -i "${PLEX_DEB}" || apt-get install -f -y
        rm -f "${PLEX_DEB}"
    fi
else
    echo "  Plex already installed, skipping."
fi

# Create NAS media mount point
mkdir -p /media/nas
chown plex:plex /media/nas

# Plex systemd override
mkdir -p /etc/systemd/system/plexmediaserver.service.d
cat > /etc/systemd/system/plexmediaserver.service.d/override.conf << 'EOF'
[Service]
LimitNOFILE=65536
EOF

systemctl enable plexmediaserver.service

# Plex auto-update
install -m 755 "${STAGING}/config/harbouros-plex-update.sh" /usr/local/bin/harbouros-plex-update.sh
cp "${STAGING}/config/harbouros-plex-update.service" /etc/systemd/system/harbouros-plex-update.service
cp "${STAGING}/config/harbouros-plex-update.timer" /etc/systemd/system/harbouros-plex-update.timer
systemctl enable harbouros-plex-update.timer

# =============================================
# Stage 2: Install HarbourOS Admin UI
# =============================================
echo ""
echo "[3/7] Installing HarbourOS Admin UI..."

mkdir -p /opt/harbouros
cp -r "${STAGING}/harbouros_admin" /opt/harbouros/harbouros_admin
cp "${STAGING}/requirements.txt" /opt/harbouros/requirements.txt

# Create virtual environment
if [ ! -d /opt/harbouros/venv ]; then
    python3 -m venv /opt/harbouros/venv
fi
/opt/harbouros/venv/bin/pip install --no-cache-dir -r /opt/harbouros/requirements.txt

# Create config directory and defaults
mkdir -p /etc/harbouros

if [ ! -f /etc/harbouros/mounts.json ]; then
    echo '{"mounts": []}' > /etc/harbouros/mounts.json
    chmod 644 /etc/harbouros/mounts.json
fi

if [ ! -f /etc/harbouros/admin.json ]; then
    HASH=$(/opt/harbouros/venv/bin/python3 -c "import bcrypt; print(bcrypt.hashpw(b'harbouros', bcrypt.gensalt()).decode())")
    cat > /etc/harbouros/admin.json << EOFAUTH
{
  "password_hash": "${HASH}",
  "password_changed": false
}
EOFAUTH
    chmod 600 /etc/harbouros/admin.json
fi

chmod 755 /etc/harbouros

# Install systemd service
cp "${STAGING}/config/harbouros.service" /etc/systemd/system/harbouros.service
systemctl enable harbouros.service

# =============================================
# Stage 3: NAS mount infrastructure
# =============================================
echo ""
echo "[4/7] Configuring NAS mount infrastructure..."
mkdir -p /media/nas
chown plex:plex /media/nas
usermod -aG plugdev plex 2>/dev/null || true

# =============================================
# Stage 4: Networking (hostname + mDNS)
# =============================================
echo ""
echo "[5/7] Configuring networking..."

CURRENT_HOSTNAME=$(hostname)
if [ "$CURRENT_HOSTNAME" != "harbouros" ]; then
    echo "harbouros" > /etc/hostname
    # Keep old hostname in /etc/hosts so sudo works before reboot
    sed -i "s/127.0.1.1.*/127.0.1.1\tharbouros\t${CURRENT_HOSTNAME}/" /etc/hosts
    echo "  Hostname changed from ${CURRENT_HOSTNAME} to harbouros (takes effect on reboot)."
else
    echo "  Hostname already set to harbouros."
fi

# Avahi mDNS service
mkdir -p /etc/avahi/services
if [ -f "${STAGING}/config/avahi/harbouros.service" ]; then
    cp "${STAGING}/config/avahi/harbouros.service" /etc/avahi/services/harbouros.service
fi
systemctl enable avahi-daemon.service

# =============================================
# Stage 5: Security hardening
# =============================================
echo ""
echo "[6/7] Applying security hardening..."

# Firewall
cp "${STAGING}/config/nftables.conf" /etc/nftables.conf
systemctl enable nftables.service

# Sysctl
cp "${STAGING}/config/sysctl-hardening.conf" /etc/sysctl.d/99-harbouros.conf
sysctl --system >/dev/null 2>&1

# SSH hardening
sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config

# Disable unused services
systemctl disable bluetooth.service 2>/dev/null || true
systemctl disable triggerhappy.service 2>/dev/null || true
systemctl disable apt-daily-upgrade.timer 2>/dev/null || true
systemctl disable apt-daily.timer 2>/dev/null || true

# =============================================
# Stage 6: Boot config + first-boot service
# =============================================
echo ""
echo "[7/7] Configuring boot..."

# Reduce GPU memory (headless)
if [ -f /boot/firmware/config.txt ]; then
    grep -q "gpu_mem=" /boot/firmware/config.txt || echo "gpu_mem=16" >> /boot/firmware/config.txt
    grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt || echo "dtoverlay=disable-bt" >> /boot/firmware/config.txt
fi

# Quiet boot
if [ -f /boot/firmware/cmdline.txt ]; then
    grep -q "quiet" /boot/firmware/cmdline.txt || sed -i 's/$/ quiet loglevel=3/' /boot/firmware/cmdline.txt
fi

# First-boot service
cp "${STAGING}/config/harbouros-firstboot.service" /etc/systemd/system/harbouros-firstboot.service
systemctl enable harbouros-firstboot.service

# =============================================
# Start services
# =============================================
echo ""
echo "Starting services..."
systemctl daemon-reload
systemctl restart nftables.service

if [ "${PLEX_ALREADY_RUNNING}" -eq 0 ]; then
    systemctl start plexmediaserver.service
fi

systemctl start harbouros.service

sleep 2

# Health check
if systemctl is-active --quiet harbouros.service; then
    echo "  harbouros is running."
else
    echo "  WARNING: harbouros failed to start!"
    systemctl status harbouros.service --no-pager || true
fi

if [ "${PLEX_ALREADY_RUNNING}" -eq 1 ]; then
    echo "  plexmediaserver is running (managed externally)."
elif systemctl is-active --quiet plexmediaserver.service; then
    echo "  plexmediaserver is running."
else
    echo "  WARNING: plexmediaserver failed to start!"
fi

# =============================================
# Cleanup
# =============================================
rm -rf "${STAGING}"

echo ""
echo "========================================="
echo "  HarbourOS installed successfully!"
echo ""
echo "  Admin UI:  http://harbouros.local:8080"
echo "  Plex:      http://harbouros.local:32400/web"
echo "  Password:  harbouros (change on first login)"
echo ""
echo "  Reboot recommended: sudo reboot"
echo "========================================="
