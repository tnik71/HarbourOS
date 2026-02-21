#!/bin/bash
set -euo pipefail

# HarbourOS — Migrate Docker Plex to Native Plex
# Preserves all settings, libraries, watch history, and metadata
# Usage: Run on the Pi as root (pushed via make migrate-plex PI=<host>)

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
    echo "[DRY RUN] No changes will be made."
    echo ""
fi

NATIVE_PLEX_DIR="/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"
BACKUP_DIR="/var/tmp"

echo "========================================="
echo "  HarbourOS — Docker Plex Migration"
echo "========================================="
echo ""

# --- Sanity checks ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must run as root."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is not installed. Is this the right machine?"
    exit 1
fi

# =============================================
# Step 1: Find Docker Plex container and data
# =============================================
echo "[1/8] Finding Docker Plex container..."

CONTAINER_ID=""
CONTAINER_NAME=""

# Find Plex container by image name
for c in $(docker ps -a --format '{{.ID}}'); do
    IMAGE=$(docker inspect --format '{{.Config.Image}}' "$c" 2>/dev/null || true)
    if echo "$IMAGE" | grep -qi "plex"; then
        CONTAINER_ID="$c"
        CONTAINER_NAME=$(docker inspect --format '{{.Name}}' "$c" | sed 's|^/||')
        break
    fi
done

if [ -z "$CONTAINER_ID" ]; then
    echo "ERROR: No Plex Docker container found."
    echo "  Checked all containers for images containing 'plex'."
    echo "  If your Plex container uses a different image name, please contact support."
    exit 1
fi

echo "  Found container: ${CONTAINER_NAME} (${CONTAINER_ID})"
echo "  Image: $(docker inspect --format '{{.Config.Image}}' "$CONTAINER_ID")"

# Find the Plex data directory from Docker volume mounts
DOCKER_PLEX_DATA=""

# Check Docker volume mounts for the config/data directory
while IFS= read -r mount; do
    SOURCE=$(echo "$mount" | cut -d: -f1)
    DEST=$(echo "$mount" | cut -d: -f2)
    # linuxserver/plex uses /config as the data mount
    if [ "$DEST" = "/config" ] || [ "$DEST" = "/data" ]; then
        if [ -d "$SOURCE" ]; then
            # Look for Plex data inside
            if [ -d "${SOURCE}/Library/Application Support/Plex Media Server" ]; then
                DOCKER_PLEX_DATA="${SOURCE}/Library/Application Support/Plex Media Server"
            elif [ -f "${SOURCE}/Preferences.xml" ]; then
                DOCKER_PLEX_DATA="${SOURCE}"
            fi
        fi
    fi
done < <(docker inspect --format '{{range .Mounts}}{{.Source}}:{{.Destination}}{{"\n"}}{{end}}' "$CONTAINER_ID" 2>/dev/null)

# Fallback: check common CasaOS paths
if [ -z "$DOCKER_PLEX_DATA" ]; then
    for path in \
        "/DATA/AppData/big-bear-plex/Library/Application Support/Plex Media Server" \
        "/DATA/AppData/plex/Library/Application Support/Plex Media Server" \
        "/opt/casaos/apps/big-bear-plex/Library/Application Support/Plex Media Server" \
        "/var/lib/docker/volumes/plex-config/_data/Library/Application Support/Plex Media Server"; do
        if [ -d "$path" ] && [ -f "${path}/Preferences.xml" ]; then
            DOCKER_PLEX_DATA="$path"
            break
        fi
    done
fi

if [ -z "$DOCKER_PLEX_DATA" ]; then
    echo "ERROR: Could not find Plex data directory."
    echo ""
    echo "  Checked Docker volume mounts and common CasaOS paths."
    echo "  Please find the directory containing Preferences.xml and run:"
    echo "    PLEX_DATA=/path/to/Plex\\ Media\\ Server $0"
    exit 1
fi

# Allow manual override
DOCKER_PLEX_DATA="${PLEX_DATA:-$DOCKER_PLEX_DATA}"

echo "  Plex data: ${DOCKER_PLEX_DATA}"

# =============================================
# Step 2: Verify Plex data
# =============================================
echo ""
echo "[2/8] Verifying Plex data..."

if [ ! -f "${DOCKER_PLEX_DATA}/Preferences.xml" ]; then
    echo "ERROR: Preferences.xml not found in ${DOCKER_PLEX_DATA}"
    exit 1
fi

# Extract server info from Preferences.xml
SERVER_NAME=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('${DOCKER_PLEX_DATA}/Preferences.xml')
print(tree.getroot().get('FriendlyName', 'Unknown'))
" 2>/dev/null || echo "Unknown")

PLEX_TOKEN=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('${DOCKER_PLEX_DATA}/Preferences.xml')
print(tree.getroot().get('PlexOnlineToken', ''))
" 2>/dev/null || echo "")

echo "  Server name: ${SERVER_NAME}"
if [ -n "$PLEX_TOKEN" ]; then
    echo "  Plex token:  found (will be preserved)"
else
    echo "  Plex token:  NOT FOUND (will need re-auth)"
fi

# Calculate data size
DATA_SIZE=$(du -sh "${DOCKER_PLEX_DATA}" 2>/dev/null | cut -f1)
echo "  Data size:   ${DATA_SIZE}"

if [ "$DRY_RUN" -eq 1 ]; then
    echo ""
    echo "[DRY RUN] Would proceed with migration. Exiting."
    echo ""
    echo "  Container:  ${CONTAINER_NAME}"
    echo "  Source:      ${DOCKER_PLEX_DATA}"
    echo "  Destination: ${NATIVE_PLEX_DIR}"
    echo "  Data size:   ${DATA_SIZE}"
    echo ""
    echo "  Run without --dry-run to execute migration."
    exit 0
fi

# =============================================
# Step 3: Create backup
# =============================================
echo ""
echo "[3/8] Creating backup..."

BACKUP_FILE="${BACKUP_DIR}/plex-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
echo "  Backing up to ${BACKUP_FILE}..."
echo "  This may take a while for large libraries..."

tar czf "${BACKUP_FILE}" -C "$(dirname "${DOCKER_PLEX_DATA}")" "$(basename "${DOCKER_PLEX_DATA}")"

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "  Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# =============================================
# Step 4: Stop Docker Plex
# =============================================
echo ""
echo "[4/8] Stopping Docker Plex..."

CONTAINER_RUNNING=$(docker inspect --format '{{.State.Running}}' "$CONTAINER_ID" 2>/dev/null || echo "false")
if [ "$CONTAINER_RUNNING" = "true" ]; then
    docker stop "$CONTAINER_ID"
    echo "  Container stopped."
else
    echo "  Container was already stopped."
fi

# Prevent Docker from restarting it
docker update --restart=no "$CONTAINER_ID" 2>/dev/null || true
echo "  Auto-restart disabled."

# =============================================
# Step 5: Install native Plex
# =============================================
echo ""
echo "[5/8] Installing native Plex..."

if dpkg -l plexmediaserver >/dev/null 2>&1; then
    echo "  Native Plex already installed."
else
    echo "  Downloading latest Plex .deb for arm64..."

    # Remove stale apt repo if present
    rm -f /etc/apt/sources.list.d/plexmediaserver.list

    PLEX_URL=$(curl -fsSL 'https://plex.tv/api/downloads/5.json' | \
        python3 -c "import sys,json; d=json.load(sys.stdin); releases=d['computer']['Linux']['releases']; deb=[r for r in releases if r.get('distro')=='debian' and 'arm64' in r.get('url','')]; print(deb[0]['url'] if deb else '')")

    if [ -z "$PLEX_URL" ]; then
        echo "ERROR: Could not find Plex ARM64 download URL."
        echo "  Starting Docker Plex back up..."
        docker start "$CONTAINER_ID"
        docker update --restart=unless-stopped "$CONTAINER_ID" 2>/dev/null || true
        exit 1
    fi

    echo "  URL: ${PLEX_URL}"
    PLEX_DEB="/tmp/plexmediaserver.deb"
    curl -fSL -o "${PLEX_DEB}" "${PLEX_URL}"
    dpkg -i "${PLEX_DEB}" || apt-get install -f -y
    rm -f "${PLEX_DEB}"
    echo "  Plex installed."
fi

# Stop native Plex before overwriting data (it creates defaults on first start)
systemctl stop plexmediaserver 2>/dev/null || true

# Setup systemd override
mkdir -p /etc/systemd/system/plexmediaserver.service.d
cat > /etc/systemd/system/plexmediaserver.service.d/override.conf << 'EOF'
[Service]
LimitNOFILE=65536
EOF

# =============================================
# Step 6: Copy Plex data
# =============================================
echo ""
echo "[6/8] Copying Plex data to native location..."
echo "  This may take a while for large libraries..."

# Ensure target directory exists
mkdir -p "${NATIVE_PLEX_DIR}"

# Copy data (preserve timestamps and permissions)
rsync -a --info=progress2 "${DOCKER_PLEX_DATA}/" "${NATIVE_PLEX_DIR}/"

echo "  Copy complete."

# =============================================
# Step 7: Fix permissions
# =============================================
echo ""
echo "[7/8] Fixing permissions..."

chown -R plex:plex /var/lib/plexmediaserver
chmod -R 755 /var/lib/plexmediaserver

# Create NAS mount point (for library paths)
mkdir -p /media/nas
chown plex:plex /media/nas

echo "  Permissions set (plex:plex)."

# =============================================
# Step 8: Start native Plex
# =============================================
echo ""
echo "[8/8] Starting native Plex..."

systemctl daemon-reload
systemctl enable plexmediaserver.service
systemctl start plexmediaserver.service

# Wait for Plex to start
echo "  Waiting for Plex to start..."
for i in $(seq 1 30); do
    if curl -sf "http://localhost:32400/identity" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

# Health check
if systemctl is-active --quiet plexmediaserver.service; then
    NATIVE_VERSION=$(dpkg-query -W -f='${Version}' plexmediaserver 2>/dev/null || echo "unknown")
    echo "  Plex is running! Version: ${NATIVE_VERSION}"
else
    echo "  WARNING: Plex may not have started correctly."
    echo "  Check: systemctl status plexmediaserver"
fi

# Check if Plex API responds
if curl -sf "http://localhost:32400/identity" >/dev/null 2>&1; then
    echo "  Plex API responding on port 32400."
else
    echo "  WARNING: Plex API not responding yet. It may still be starting up."
    echo "  Check: curl http://localhost:32400/identity"
fi

# =============================================
# Summary
# =============================================
IP_ADDR=$(hostname -I | awk '{print $1}')

echo ""
echo "========================================="
echo "  Migration Complete!"
echo "========================================="
echo ""
echo "  Plex Web UI:  http://${IP_ADDR}:32400/web"
echo "  HarbourOS:    http://${IP_ADDR}:8080"
echo ""
echo "  Backup:       ${BACKUP_FILE}"
echo ""
echo "  IMPORTANT: Check your Plex Web UI to verify:"
echo "  - All libraries are present"
echo "  - Watch history is intact"
echo "  - Library paths are correct"
echo ""
echo "  If library paths use Docker mount points (e.g. /data/...),"
echo "  update them in Plex Settings → Libraries to use /media/nas/..."
echo ""
echo "  Docker Plex container '${CONTAINER_NAME}' is stopped but NOT removed."
echo "  To rollback:  docker start ${CONTAINER_ID}"
echo "  To remove:    docker rm ${CONTAINER_ID}"
echo "========================================="
