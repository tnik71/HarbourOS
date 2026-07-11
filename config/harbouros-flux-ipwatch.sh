#!/bin/bash
# Detects external IP changes and updates Flux/fluxbench configs automatically.
set -euo pipefail

LOG="/var/log/harbouros-flux-ipwatch.log"
FLUX_CONF="/var/lib/fluxd/flux.conf"
BENCH_CONF="/var/lib/fluxbench/fluxbench.conf"
IP_CACHE="/etc/harbouros/.flux-last-ip"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG"; }

# Fetch current external IP
CURRENT_IP=$(curl -sf --max-time 10 https://api.ipify.org 2>/dev/null || \
             curl -sf --max-time 10 https://ifconfig.me 2>/dev/null || \
             curl -sf --max-time 10 https://icanhazip.com 2>/dev/null || true)

if [ -z "$CURRENT_IP" ]; then
    log "ERROR: Could not determine external IP address."
    exit 1
fi

# Read last known IP
LAST_IP=""
if [ -f "$IP_CACHE" ]; then
    LAST_IP=$(cat "$IP_CACHE")
fi

if [ "$CURRENT_IP" = "$LAST_IP" ]; then
    exit 0
fi

log "IP change detected: ${LAST_IP:-none} -> ${CURRENT_IP}"

# Update flux.conf
python3 - <<PYEOF
import re
path = '$FLUX_CONF'
new_ip = '$CURRENT_IP'
with open(path) as f:
    content = f.read()
if re.search(r'^externalip=', content, re.MULTILINE):
    content = re.sub(r'^externalip=.*$', f'externalip={new_ip}', content, flags=re.MULTILINE)
else:
    content += f'\nexternalip={new_ip}\n'
with open(path, 'w') as f:
    f.write(content)
PYEOF
log "Updated externalip in flux.conf"

# Update fluxbench.conf
python3 - <<PYEOF
import re
path = '$BENCH_CONF'
new_ip = '$CURRENT_IP'
with open(path) as f:
    content = f.read()
if re.search(r'^externalip=', content, re.MULTILINE):
    content = re.sub(r'^externalip=.*$', f'externalip={new_ip}', content, flags=re.MULTILINE)
else:
    content += f'\nexternalip={new_ip}\n'
with open(path, 'w') as f:
    f.write(content)
PYEOF
log "Updated externalip in fluxbench.conf"

# Restart fluxd
log "Restarting zelcash..."
systemctl restart zelcash
sleep 30

# Restart fluxbenchd
log "Restarting fluxbenchd..."
systemctl restart fluxbenchd
sleep 5

# Restart FluxOS so it picks up the new IP
log "Restarting FluxOS..."
PM2_HOME=/root/.pm2 pm2 restart flux --update-env
sleep 10

# Re-register node with new IP — wait for fluxd to finish loading
log "Waiting for fluxd block index..."
for i in $(seq 1 12); do
    sleep 10
    STATUS=$(flux-cli -conf="$FLUX_CONF" getzelnodestatus 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null || echo "loading")
    if [ "$STATUS" != "loading" ]; then
        break
    fi
done
log "Broadcasting startdeterministicfluxnode..."
flux-cli -conf="$FLUX_CONF" startdeterministicfluxnode harbouros false 2>&1 | tee -a "$LOG" || \
    log "WARNING: startdeterministicfluxnode failed — node may need to be started manually"

# Save new IP
echo "$CURRENT_IP" > "$IP_CACHE"
log "IP update complete. New IP: ${CURRENT_IP}"

# Trim log to last 300 lines
TMPLOG=$(mktemp "${LOG}.XXXXXX") && tail -300 "$LOG" > "$TMPLOG" && mv "$TMPLOG" "$LOG"
