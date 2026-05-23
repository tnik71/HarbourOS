#!/bin/bash
set -euo pipefail
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
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"
}

fail() {
    log "ERROR: $1"
    TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
    exit 1
}

log "Checking for HarbourOS updates..."

# --- Ensure repo clone exists ---
if [ ! -d "${REPO_DIR}/.git" ]; then
    log "No local repo found. Cloning from GitHub..."
    # Use -c safe.directory on clone destination parent, then fix ownership after
    git clone --branch "${BRANCH}" --single-branch "${GITHUB_REPO}" "${REPO_DIR}" >> "$LOG" 2>&1 \
        || fail "git clone failed."
    log "Initial clone complete."
fi

# --- Safe.directory: grant root access to repo owned by harbouros user.
# Git 2.35.2+ refuses to operate on repos owned by a different UID.
# We use -c safe.directory=<path> on every git command rather than writing
# to --global config (HOME varies across sudo contexts and creates duplicates).
# The alias below ensures every git invocation carries the flag.
GIT="git -c safe.directory=${REPO_DIR}"

# Verify the alias actually works before proceeding — fail loudly if not.
if ! $GIT -C "${REPO_DIR}" rev-parse HEAD > /dev/null 2>&1; then
    fail "git rev-parse HEAD failed — repo at ${REPO_DIR} is inaccessible. Check ownership."
fi

# --- Read current state ---
OLD_VERSION="unknown"
if [ -f "${REPO_DIR}/VERSION" ]; then
    OLD_VERSION=$(tr -d '[:space:]' < "${REPO_DIR}/VERSION")
fi
LOCAL_SHA=$($GIT -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null) \
    || fail "Could not read LOCAL HEAD SHA."

log "Current: version=${OLD_VERSION} sha=${LOCAL_SHA:0:8}"

# --- Fetch latest from GitHub ---
log "Fetching origin/${BRANCH}..."
$GIT -C "${REPO_DIR}" fetch origin "${BRANCH}" >> "$LOG" 2>&1 \
    || fail "git fetch failed — network issue or GitHub unreachable."

REMOTE_SHA=$($GIT -C "${REPO_DIR}" rev-parse "origin/${BRANCH}" 2>/dev/null) \
    || fail "Could not read REMOTE HEAD SHA after fetch."

REMOTE_VERSION=$($GIT -C "${REPO_DIR}" show "origin/${BRANCH}:VERSION" 2>/dev/null | tr -d '[:space:]') \
    || REMOTE_VERSION="unknown"

log "Remote: version=${REMOTE_VERSION} sha=${REMOTE_SHA:0:8}"

# --- Up to date? ---
if [ "${LOCAL_SHA}" = "${REMOTE_SHA}" ]; then
    log "HarbourOS is up to date (${OLD_VERSION}, ${LOCAL_SHA:0:8}). No action needed."
    mkdir -p /var/lib/harbouros
    cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": false, "current_version": "${OLD_VERSION}", "current_sha": "${LOCAL_SHA:0:8}", "last_check": "$(date -Iseconds)"}
EOF
    TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
    exit 0
fi

# --- Update available ---
log "Update available: ${OLD_VERSION} (${LOCAL_SHA:0:8}) -> ${REMOTE_VERSION} (${REMOTE_SHA:0:8})"

mkdir -p /var/lib/harbouros
cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": true, "current_version": "${OLD_VERSION}", "current_sha": "${LOCAL_SHA:0:8}", "new_version": "${REMOTE_VERSION}", "new_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)"}
EOF

if [ "${CHECK_ONLY}" -eq 1 ]; then
    log "Check-only mode: update available but not applying."
    TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
    exit 0
fi

# --- Apply update ---
log "Applying update: ${OLD_VERSION} -> ${REMOTE_VERSION}..."
ROLLBACK_SHA="${LOCAL_SHA}"

# Reset to remote — this is the step that was silently failing before.
# We check the exit code explicitly AND verify HEAD afterwards.
$GIT -C "${REPO_DIR}" reset --hard "origin/${BRANCH}" >> "$LOG" 2>&1 \
    || fail "git reset --hard origin/${BRANCH} failed. Repo may have local conflicts or ownership issues. No files were changed."

# Verify HEAD now matches REMOTE_SHA — guards against partial reset.
ACTUAL_SHA=$($GIT -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null) \
    || fail "Could not read HEAD after reset."
if [ "${ACTUAL_SHA}" != "${REMOTE_SHA}" ]; then
    fail "HEAD mismatch after reset: expected ${REMOTE_SHA:0:8}, got ${ACTUAL_SHA:0:8}. Aborting deploy."
fi

# Verify the VERSION file on disk now matches what we expect.
DISK_VERSION=$(tr -d '[:space:]' < "${REPO_DIR}/VERSION" 2>/dev/null) || DISK_VERSION=""
if [ -n "${REMOTE_VERSION}" ] && [ "${REMOTE_VERSION}" != "unknown" ] && [ "${DISK_VERSION}" != "${REMOTE_VERSION}" ]; then
    fail "VERSION file mismatch after reset: expected ${REMOTE_VERSION}, got '${DISK_VERSION}'. Aborting deploy."
fi

NEW_VERSION="${DISK_VERSION}"
log "Git reset verified: HEAD=${ACTUAL_SHA:0:8}, VERSION=${NEW_VERSION}"

# --- Stage files ---
STAGING="/tmp/harbouros-deploy"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/harbouros_admin"
mkdir -p "${STAGING}/config"

cp -r "${REPO_DIR}/admin-ui/harbouros_admin/"* "${STAGING}/harbouros_admin/"
cp "${REPO_DIR}/admin-ui/requirements.txt" "${STAGING}/requirements.txt"
cp -r "${REPO_DIR}/config/"* "${STAGING}/config/"
cp "${REPO_DIR}/scripts/apply-update.sh" "${STAGING}/apply-update.sh"
chmod +x "${STAGING}/apply-update.sh"

# Write success status before running apply-update.sh — the apply script restarts
# harbouros.service which kills this process via the service cgroup. If apply
# fails, the rollback block below overwrites this entry with an error.
CHANGELOG=$($GIT -C "${REPO_DIR}" log --oneline "${LOCAL_SHA}..${REMOTE_SHA}" 2>/dev/null \
    | head -20 | sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n')
cat > /var/lib/harbouros/update-status.json << EOF
{"update_available": false, "current_version": "${NEW_VERSION}", "current_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)", "last_update": "$(date -Iseconds)", "previous_version": "${OLD_VERSION}", "changelog": "${CHANGELOG}"}
EOF

# --- Run apply script ---
log "Running apply-update.sh..."
"${STAGING}/apply-update.sh" >> "$LOG" 2>&1
APPLY_EXIT=$?

if [ ${APPLY_EXIT} -ne 0 ]; then
    log "ERROR: apply-update.sh failed (exit ${APPLY_EXIT}). Rolling back to ${OLD_VERSION} (${ROLLBACK_SHA:0:8})..."

    $GIT -C "${REPO_DIR}" reset --hard "${ROLLBACK_SHA}" >> "$LOG" 2>&1 || \
        log "WARNING: rollback git reset also failed — repo may be in inconsistent state."

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
{"update_available": true, "current_version": "${OLD_VERSION}", "current_sha": "${ROLLBACK_SHA:0:8}", "new_version": "${REMOTE_VERSION}", "new_sha": "${REMOTE_SHA:0:8}", "last_check": "$(date -Iseconds)", "last_error": "Update failed (apply-update.sh exit ${APPLY_EXIT}), rolled back automatically."}
EOF
    TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
    exit 1
fi

log "Update complete: ${OLD_VERSION} -> ${NEW_VERSION} (${REMOTE_SHA:0:8})"
TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
