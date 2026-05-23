#!/bin/bash
# HarbourOS FluxOS P2SH compatibility patches (LEGACY / EMERGENCY USE ONLY)
#
# NOTE: These patches are NOT the primary supported deployment mode.
# The official HarbourOS Flux configuration uses insightexplorer=1 in flux.conf,
# which routes FluxOS through the processInsight() code path and avoids P2SH
# crashes entirely — no source patching required.
#
# This script exists as a fallback for environments where insightexplorer=1 cannot
# be used (e.g. fresh installs still syncing, rollback situations). If your node
# was set up using harbouros-flux-install.sh and flux.conf contains
# insightexplorer=1, you do not need to run this script.
#
# Safe to run multiple times (idempotent).
# Also installs a git post-merge hook so patches survive FluxOS auto-updates.

set -euo pipefail

EXPLORER="/opt/flux/ZelBack/src/services/explorerService.js"
NETWORK="/opt/flux/ZelBack/src/services/fluxNetworkHelper.js"
PATCH_FLAG="/etc/harbouros/.flux-patches-applied"

if [ ! -f "$EXPLORER" ] || [ ! -f "$NETWORK" ]; then
    echo "FluxOS not installed at /opt/flux, skipping patches."
    exit 0
fi

echo "Applying HarbourOS FluxOS patches..."

EXPLORER_CHANGED=0

# Patch 1: explorerService.js — null-safe txContent check
# Fixes crash when P2SH transaction inputs are not in the local UTXO database.
python3 - "$EXPLORER" << 'EOF'
import sys
path = sys.argv[1]
content = open(path).read()
old = '  const txContent = await dbHelper.findOneAndDeleteInDatabase(database, utxoIndexCollection, query, projection);\n  if (!txContent.value) {'
new = '  const txContent = await dbHelper.findOneAndDeleteInDatabase(database, utxoIndexCollection, query, projection);\n  if (!txContent || !txContent.value) {'
if old in content:
    open(path, 'w').write(content.replace(old, new))
    print("  [1/4] txContent null check: patched")
    sys.exit(1)  # signal change
else:
    print("  [1/4] txContent null check: already applied")
    sys.exit(0)
EOF
[ $? -ne 0 ] && EXPLORER_CHANGED=1 || true

# Patch 2: explorerService.js — null-safe sender.vout check
# Fixes crash when getSenderTransactionFromDaemon returns null for P2SH inputs.
python3 - "$EXPLORER" << 'EOF'
import sys
path = sys.argv[1]
content = open(path).read()
old = '    const sender = await getSenderTransactionFromDaemon(txid);\n    const senderData = sender.vout[vout];'
new = '    const sender = await getSenderTransactionFromDaemon(txid);\n    if (!sender || !sender.vout || !sender.vout[vout]) { return { address: "unknown" }; }\n    const senderData = sender.vout[vout];'
if old in content:
    open(path, 'w').write(content.replace(old, new))
    print("  [2/4] sender.vout null check: patched")
    sys.exit(1)
else:
    print("  [2/4] sender.vout null check: already applied")
    sys.exit(0)
EOF
[ $? -ne 0 ] && EXPLORER_CHANGED=1 || true

# Patch 3: explorerService.js — null-safe scriptPubKey.addresses access
# Fixes crash reading addresses from P2SH scriptPubKey which lacks the addresses array.
python3 - "$EXPLORER" << 'EOF'
import sys
path = sys.argv[1]
content = open(path).read()
old = '      address: senderData.scriptPubKey.addresses[0], // always exists as it is utxo.'
new = '      address: (senderData.scriptPubKey.addresses && senderData.scriptPubKey.addresses[0]) || senderData.scriptPubKey.address || "unknown",'
if old in content:
    open(path, 'w').write(content.replace(old, new))
    print("  [3/4] scriptPubKey.addresses null check: patched")
    sys.exit(1)
else:
    print("  [3/4] scriptPubKey.addresses null check: already applied")
    sys.exit(0)
EOF
[ $? -ne 0 ] && EXPLORER_CHANGED=1 || true

# Patch 4: fluxNetworkHelper.js — IP fallback to userconfig when benchmark fails
# Fixes "Flux IP not detected" when fluxbenchd can't complete benchmarks because
# the node isn't confirmed yet (chicken-and-egg on first start).
python3 - "$NETWORK" << 'EOF'
import sys
path = sys.argv[1]
content = open(path).read()
old = '  const ip = status === \'success\' ? ipaddress : null;'
new = '  const ip = status === \'success\' ? ipaddress : (userconfig.initial.ipaddress || null);'
if old in content:
    open(path, 'w').write(content.replace(old, new))
    print("  [4/4] IP fallback to userconfig: patched")
elif 'userconfig.initial.ipaddress || null' in content:
    print("  [4/4] IP fallback to userconfig: already applied")
else:
    print("  [4/4] IP fallback to userconfig: pattern not found, manual check needed")
EOF

# If explorerService.js was changed for the first time, wipe the FluxOS MongoDB
# database so it rebuilds cleanly without corrupt P2SH state.
if [ "$EXPLORER_CHANGED" -eq 1 ] && [ ! -f "$PATCH_FLAG" ]; then
    echo "  First-time patch: wiping zelfluxlocal database to clear corrupt P2SH state..."
    mongosh --eval 'use zelfluxlocal; db.dropDatabase()' 2>/dev/null || \
        mongo --eval 'use zelfluxlocal; db.dropDatabase()' 2>/dev/null || \
        echo "  (mongosh not available, skipping DB wipe)"
    mkdir -p "$(dirname "$PATCH_FLAG")"
    touch "$PATCH_FLAG"
fi

# Patch 5: fluxbench.conf — fix RPC credentials to match FluxOS expectations
# FluxOS benchmarkService.js uses fluxbenchuser/fluxbenchpassword but the multitool
# may write different credentials, causing "incorrect password" errors every 30s.
BENCH_CONF="/var/lib/fluxbench/fluxbench.conf"
if [ -f "$BENCH_CONF" ]; then
    NEEDS_FIX=0
    grep -q '^rpcuser=fluxbenchuser$' "$BENCH_CONF" || NEEDS_FIX=1
    grep -q '^rpcpassword=fluxbenchpassword$' "$BENCH_CONF" || NEEDS_FIX=1
    if [ "$NEEDS_FIX" -eq 1 ]; then
        sed -i 's/^rpcuser=.*/rpcuser=fluxbenchuser/' "$BENCH_CONF"
        sed -i 's/^rpcpassword=.*/rpcpassword=fluxbenchpassword/' "$BENCH_CONF"
        sudo systemctl restart fluxbenchd 2>/dev/null || true
        echo "  [5/5] fluxbenchd credentials: patched"
    else
        echo "  [5/5] fluxbenchd credentials: already correct"
    fi
fi

# Install git post-merge hook so patches survive FluxOS watchdog auto-updates.
# The watchdog does: git reset --hard origin/master && git pull
# The post-merge hook fires after git pull and re-applies our patches before pm2 restarts flux.
HOOK="/opt/flux/.git/hooks/post-merge"
if [ -d "/opt/flux/.git/hooks" ]; then
    cat > "$HOOK" << 'HOOK_EOF'
#!/bin/bash
# Installed by HarbourOS — re-applies P2SH patches after FluxOS git pull
if [ -x /usr/local/bin/harbouros-flux-patch.sh ]; then
    echo "[$(date)] FluxOS updated — re-applying HarbourOS patches..." >> /var/log/harbouros-flux-patch.log
    /usr/local/bin/harbouros-flux-patch.sh >> /var/log/harbouros-flux-patch.log 2>&1
fi
exit 0
HOOK_EOF
    chmod +x "$HOOK"
    echo "  [hook] post-merge hook installed at $HOOK"
fi

echo "Restarting FluxOS..."
pm2 restart flux 2>/dev/null || true

echo "HarbourOS FluxOS patches applied."
