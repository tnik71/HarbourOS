#!/bin/bash
# HarbourOS — Automatic Plex Media Server update (direct .deb download)
LOG="/var/log/harbouros-plex-update.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') Checking for Plex updates..." >> "$LOG"

OLD_VER=$(dpkg-query -W -f='${Version}' plexmediaserver 2>/dev/null || echo "unknown")

# Get latest Plex ARM64 .deb URL
PLEX_URL=$(curl -fsSL 'https://plex.tv/api/downloads/5.json' 2>>"$LOG" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); releases=d['computer']['Linux']['releases']; deb=[r for r in releases if r.get('distro')=='debian' and 'arm64' in r.get('url','')]; print(deb[0]['url'] if deb else '')" 2>>"$LOG")

if [ -z "$PLEX_URL" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') ERROR: Could not find Plex download URL." >> "$LOG"
    exit 1
fi

# Extract version from URL to check if update is needed
LATEST_VER=$(echo "$PLEX_URL" | grep -oP 'plexmediaserver_\K[^_]+' || echo "")

if [ "$OLD_VER" = "$LATEST_VER" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Plex is up to date ($OLD_VER). No action needed." >> "$LOG"
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Downloading update: ${PLEX_URL}" >> "$LOG"
DEB="/tmp/plexmediaserver-update.deb"
curl -fSL -o "$DEB" "$PLEX_URL" >> "$LOG" 2>&1

dpkg -i "$DEB" >> "$LOG" 2>&1 || apt-get install -f -y >> "$LOG" 2>&1
rm -f "$DEB"

NEW_VER=$(dpkg-query -W -f='${Version}' plexmediaserver 2>/dev/null || echo "unknown")

if [ "$OLD_VER" != "$NEW_VER" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Updated Plex: $OLD_VER -> $NEW_VER" >> "$LOG"
    systemctl restart plexmediaserver
    echo "$(date '+%Y-%m-%d %H:%M:%S') Plex restarted." >> "$LOG"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') Install completed but version unchanged ($OLD_VER)." >> "$LOG"
fi

# Keep log file from growing forever (last 200 lines)
tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
