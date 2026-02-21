#!/bin/bash -e
# Install Plex Media Server (ARM64)

echo "HarbourOS: Installing Plex Media Server..."

# Download latest Plex ARM64 .deb directly (apt repo has SHA-1 signing issues)
PLEX_URL=$(curl -fsSL 'https://plex.tv/api/downloads/5.json' | \
    python3 -c "import sys,json; d=json.load(sys.stdin); releases=d['computer']['Linux']['releases']; deb=[r for r in releases if r.get('distro')=='debian' and 'arm64' in r.get('url','')]; print(deb[0]['url'] if deb else '')")
if [ -z "$PLEX_URL" ]; then
    echo "ERROR: Could not find Plex ARM64 download URL."
    exit 1
fi
echo "  Downloading: ${PLEX_URL}"
curl -fSL -o /tmp/plexmediaserver.deb "${PLEX_URL}"
dpkg -i /tmp/plexmediaserver.deb || apt-get install -f -y
rm -f /tmp/plexmediaserver.deb

# Create NAS media mount point
mkdir -p /media/nas
chown plex:plex /media/nas

# Create systemd override for Plex
mkdir -p /etc/systemd/system/plexmediaserver.service.d
cat > /etc/systemd/system/plexmediaserver.service.d/override.conf << 'EOF'
[Service]
LimitNOFILE=65536
EOF

# Enable Plex to start on boot
systemctl enable plexmediaserver.service

# Install automatic Plex update timer (every Friday at 1 AM)
install -m 755 /tmp/harbouros-plex-update.sh /usr/local/bin/harbouros-plex-update.sh
cp /tmp/harbouros-plex-update.service /etc/systemd/system/harbouros-plex-update.service
cp /tmp/harbouros-plex-update.timer /etc/systemd/system/harbouros-plex-update.timer
systemctl enable harbouros-plex-update.timer

echo "HarbourOS: Plex Media Server installed."
