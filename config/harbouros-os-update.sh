#!/bin/bash
set -euo pipefail
# HarbourOS — Automatic OS security updates (weekly)
LOG="/var/log/harbouros-os-update.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"; }

log "Starting OS package update..."

# Update package index
if ! apt-get update -qq >> "$LOG" 2>&1; then
    log "ERROR: apt-get update failed."
    exit 1
fi

# Count available upgrades before applying
UPGRADABLE=$(apt list --upgradable 2>/dev/null | grep -c '/' || true)
if [ "${UPGRADABLE}" -eq 0 ]; then
    log "All packages are up to date. No action needed."
    TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
    exit 0
fi

log "${UPGRADABLE} package(s) available for upgrade."

# Use upgrade (not dist-upgrade) — safer, won't remove packages
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    -o Dpkg::Options::="--force-confdef" \
    -o Dpkg::Options::="--force-confold" \
    >> "$LOG" 2>&1
EXIT_CODE=$?

if [ ${EXIT_CODE} -eq 0 ]; then
    log "OS update completed successfully. ${UPGRADABLE} package(s) upgraded."
    apt-get autoremove -y -qq >> "$LOG" 2>&1 || true
else
    log "ERROR: apt-get upgrade failed (exit ${EXIT_CODE})."
fi

# Trim log to last 200 lines
TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -200 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
exit ${EXIT_CODE}
