#!/bin/bash
# HarbourOS — Automatic self-update from GitHub
LOG="/var/log/harbouros-self-update.log"
REPO_DIR="/opt/harbouros/repo"
GITHUB_REPO="https://github.com/tnik71/HarbourOS.git"
BRANCH="main"
CHECK_ONLY=0
if [ "${1:-}" = "--check-only" ]; then
    CHECK_ONLY=1
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

log "Checking for HarbourOS updates..."

# --- Ensure repo clone exists ---
if [ ! -d "${REPO_DIR}/.git" ]; then
    log "No local repo found. Cloning from GitHub..."
    git clone --branch "${BRANCH}" --single-branch "${GITHUB_REPO}" "${REPO_DIR}" >> "$LOG" 2>&1
    if [ $? -ne 0 ]; then
        log "ERROR: git clone failed."
        exit 1
    fi
    log "Initial clone complete."
fi

cd "${REPO_DIR}"

# Allow root to operate on repo owned by harbouros user (Git 2.35.2+ safety check)
git config --global --add safe.directory "${REPO_DIR}" 2>/dev/null

# --- Read current version ---
OLD_VERSION="unknown"
if [ -f "${REPO_DIR}/VERSION" ]; then
    OLD_VERSION=$(tr -d '[:space:]' < "${REPO_DIR}/VERSION")
fi
LOCAL_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

# --- Fetch latest from GitHub ---
git fetch origin "${BRANCH}" >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    log "ERROR: git fetch failed (network issue?)."
    exit 1
fi

REMOTE_SHA=$(git rev-parse "origin/${BRANCH}" 2>/dev/null)

if [ "${LOCAL_SHA}" = "${REMOTE_SHA}" ]; then
    log "HarbourOS is up to date (${OLD_VERSION}, ${LOCAL_SHA:0:8}). No action needed."
    mkdir -p /var/lib/harbouros
    cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": false, "current_version": "${OLD_VERSION}", "current_sha": "${LOCAL_SHA:0:8}", "last_check": "$(date -Iseconds)"}
EOF
    # Keep log from growing forever
    tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    exit 0
fi

# --- Update available ---
REMOTE_VERSION=$(git show "origin/${BRANCH}:VERSION" 2>/dev/null | tr -d '[:space:]' || echo "unknown")
log "Update available: ${OLD_VERSION} (${LOCAL_SHA:0:8}) -> ${REMOTE_VERSION} (${REMOTE_SHA:0:8})"

mkdir -p /var/lib/harbouros
cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": true, "current_version": "${OLD_VERSION}", "current_sha": "${LOCAL_SHA:0:8}", "new_version": "${REMOTE_VERSION}", "new_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)"}
EOF

if [ "${CHECK_ONLY}" -eq 1 ]; then
    log "Check-only mode: update available but not applying."
    tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    exit 0
fi

# --- Apply update ---
log "Applying update..."
ROLLBACK_SHA="${LOCAL_SHA}"

git reset --hard "origin/${BRANCH}" >> "$LOG" 2>&1

# Stage files in the same layout deploy.sh uses
STAGING="/tmp/harbouros-deploy"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/harbouros_admin"
mkdir -p "${STAGING}/config"

cp -r "${REPO_DIR}/admin-ui/harbouros_admin/"* "${STAGING}/harbouros_admin/"
cp "${REPO_DIR}/admin-ui/requirements.txt" "${STAGING}/requirements.txt"
cp -r "${REPO_DIR}/config/"* "${STAGING}/config/"
cp "${REPO_DIR}/scripts/apply-update.sh" "${STAGING}/apply-update.sh"
chmod +x "${STAGING}/apply-update.sh"

# Run the same apply script that deploy.sh uses
"${STAGING}/apply-update.sh" >> "$LOG" 2>&1
APPLY_EXIT=$?

if [ ${APPLY_EXIT} -ne 0 ]; then
    log "ERROR: apply-update.sh failed (exit ${APPLY_EXIT}). Rolling back..."
    cd "${REPO_DIR}"
    git reset --hard "${ROLLBACK_SHA}" >> "$LOG" 2>&1

    # Re-stage old code and apply
    rm -rf "${STAGING}"
    mkdir -p "${STAGING}/harbouros_admin"
    mkdir -p "${STAGING}/config"
    cp -r "${REPO_DIR}/admin-ui/harbouros_admin/"* "${STAGING}/harbouros_admin/"
    cp "${REPO_DIR}/admin-ui/requirements.txt" "${STAGING}/requirements.txt"
    cp -r "${REPO_DIR}/config/"* "${STAGING}/config/"
    cp "${REPO_DIR}/scripts/apply-update.sh" "${STAGING}/apply-update.sh"
    chmod +x "${STAGING}/apply-update.sh"
    "${STAGING}/apply-update.sh" >> "$LOG" 2>&1 || true

    log "Rolled back to ${OLD_VERSION} (${ROLLBACK_SHA:0:8})."
    cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": true, "current_version": "${OLD_VERSION}", "current_sha": "${ROLLBACK_SHA:0:8}", "new_version": "${REMOTE_VERSION}", "new_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)", "last_error": "Update failed, rolled back automatically."}
EOF
    tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    exit 1
fi

# --- Success ---
NEW_VERSION=$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null || echo "unknown")
log "Updated HarbourOS: ${OLD_VERSION} -> ${NEW_VERSION} (${REMOTE_SHA:0:8})"

cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": false, "current_version": "${NEW_VERSION}", "current_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)", "last_update": "$(date -Iseconds)", "previous_version": "${OLD_VERSION}"}
EOF

# Keep log from growing forever
tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
