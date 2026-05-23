# HarbourOS Changelog

## v1.1.2 — Flux Integrity, Design System, and Reliability (2026-05-23)

### Flux Integrity

- **Upstream-only FluxOS**: HarbourOS no longer modifies FluxOS source code in any way. `harbouros-flux-patch.sh` and all associated deployment hooks have been removed.
- **Removed P2SH patch system**: The `explorerService.js` null-check patch and `fluxNetworkHelper.js` IP fallback patch are gone. P2SH compatibility is handled by `insightexplorer=1` in `flux.conf` — no source modification required.
- **Removed post-merge git hook**: The git hook that re-applied patches after every FluxOS `git pull` has been removed from `/opt/flux/.git/hooks/`.
- **Removed patch deployment from updates**: `apply-update.sh` no longer installs or runs `harbouros-flux-patch.sh` on deploy.
- **Verified clean working tree**: `git -C /opt/flux status` shows no modified tracked files. HEAD matches `origin/master` exactly (`aab617ab32`).

### Bug Fixes

- **Flux node expiration**: Fixed node expiring because FluxOS auto-update ran as root, changing log file ownership to `root`. FluxOS (running as `tnik71`) could not write logs and crashed on every pm2 restart, leaving fluxbenchd unable to complete benchmark signing. Node fell out of CONFIRMED after confirm window expired.
- **Flux benchmark recovery**: Identified and resolved fluxbenchd rejecting benchmarks with "FluxOs version Code not supported" — caused by the P2SH patch modifying `explorerService.js` and changing the directory MD5 fingerprint used by remote benchmark nodes to validate FluxOS integrity.
- **Stale fluxbenchd process**: Fixed port 16224 bind failure after `systemctl restart` caused by a stale process still holding the socket. Resolved by killing the stale PID before restart.
- **Flux install log streaming**: `start_install()` now redirects stdout/stderr to the install log via Python file handles instead of shell redirection tokens passed as positional arguments to `subprocess.Popen`. The install log was always empty before this fix.

### UI — CSS Design System

- **Design system tokens**: Added spacing scale (`--space-xs` through `--space-xl`), typography scale (`--text-xs` through `--text-2xl`), shadow tokens, and border-radius tokens to `:root`.
- **Blue-only status language**: Semantic colour variables unified — running/confirmed/active states use HarbourOS blue (`--accent`). Error and warning states use neutral gray with border emphasis. No green, amber, or red fills anywhere in the UI.
- **Hardcoded colours eliminated**: Ring gauge colours, episode card borders, progress bars, and show status badges all migrated to CSS variables.
- **Flux modal widened**: Flux Node and System Management modals expanded to 800px (`modal-lg`) for better information density.
- **Flux Status tab redesigned**: Status header with status dot + node label + tier, service health row (fluxd/FluxOS/mongod/benchd), progress bars for block sync and explorer sync, section-labelled stat grids. No coloured hero cards.
- **Flux Benchmark tab**: Pass/fail shown as `.flux-bench-result` text badge. Hardware section labelled. No inline colour styles.
- **Badge variants added**: `badge-confirmed`, `badge-running`, `badge-stopped`, `badge-expired`, `badge-offline`, `badge-installing`, `badge-syncing` — all with neutral backgrounds and blue or gray text only.
- **Install tab**: Log viewer always visible (min-height 60px) with placeholder text when no install has run. Card wrappers replaced with `flux-section-label` dividers.
- **Password warning banner**: Amber background replaced with blue-tinted glass consistent with design language.

### Security / Hygiene

- **Secret ignore rules**: Added `.env` and `**/.env` patterns to `.gitignore`.
- **System log cap**: `/api/system/logs` now enforces a 500-line server-side maximum, consistent with the Flux log endpoint.

### Documentation

- **README**: Added Flux CUMULUS node support to Features, Architecture, and Project Structure sections. Added Flux Node section covering hardware recommendation, Insight Explorer mode, benchmark/wallet monitoring, and Flux + Plex coexistence.
- **apply-update.sh**: Patch deployment step removed and replaced with a comment explaining that HarbourOS does not modify FluxOS source code.
- **harbouros-flux-node-watcher.sh**: Removed from repo — documented as a local-only recovery helper that is operator-specific and not safe to auto-deploy.

---

## v1.1.1 — Flux stability fixes (2026-05-23)

### Bug Fixes

- **Self-update**: `harbouros-self-update.sh` now exits immediately on any git failure (`set -euo pipefail`, `fail()` helper). Adds canary check before git operations, explicit `git fetch` and `git reset --hard` failure handling, post-reset HEAD SHA and VERSION file verification. Previously a `safe.directory` ownership error could silently leave the repo at an old revision and deploy stale code.
- **Self-update log ownership**: `apply-update.sh` now ensures `/var/log/harbouros-self-update.log` is owned by `harbouros:harbouros` on every deploy so the admin UI can read it.
- **Benchmark display**: Corrected `passed` field logic — `getbenchmarks` returns `status: "CUMULUS"` when passing, never `"ok"`. Fixed to treat any status other than `null`, `"failed"`, or `"running"` as passed.
- **Watchdog defaults**: `web_hook_url` default is `'0'` (disabled) to prevent Discord webhook errors on installs without a configured webhook URL. `zelflux_update: '1'` ensures FluxOS auto-updates are enabled by default.

### Infrastructure

- FluxOS source patching (`harbouros-flux-patch.sh`) clarified as LEGACY/EMERGENCY USE ONLY. Standard deployments use `insightexplorer=1` which eliminates P2SH crashes without patching FluxOS source.
- `fluxbench-cli` commands throughout use `-datadir=/var/lib/fluxbench` flag consistently.
- `flux-cli` commands use `-datadir=/var/lib/fluxd` flag consistently.

---

## v1.1.0 — Flux Node Support (2026-05-23)

### New Features

**Production Flux Node Support**
- Full Flux CUMULUS node deployment on Raspberry Pi 5 with NVMe
- Insight Explorer mode (`insightexplorer=1`) as the standard deployment configuration, eliminating FluxOS P2SH transaction crashes without source patching
- Flux node installer script (`harbouros-flux-install.sh`) with pre-flight hardware checks (RAM, disk speed), Docker installation, FluxOS multitool integration, and automatic `flux.conf` generation
- `flux.conf` generated with all required Insight Explorer flags: `insightexplorer=1`, `experimentalfeatures=1`, `addressindex=1`, `timestampindex=1`, `spentindex=1`
- Correct `zelcash.service` using explicit `-datadir=/var/lib/fluxd -conf=/var/lib/fluxd/flux.conf` flags, eliminating config path ambiguity
- `fluxbenchd` RPC credential auto-correction (`fluxbenchuser`/`fluxbenchpassword`) matching FluxOS `benchmarkService.js` expectations

**Flux Node Dashboard Tab**
- Node status card (CONFIRMED / STARTED / EXPIRED / OFFLINE)
- Tier display (CUMULUS / NIMBUS / STRATUS)
- Block height and sync percentage with live network height
- Benchmark results: CPU cores, RAM, disk write speed, EPS, download/upload speeds
- Docker container count
- Wallet balance with collateral note
- Reward tracking: earned today, earned total, last payout date, payout count
- Explorer scanned height (Insight Explorer indexing progress)
- Node action buttons: Start, Stop, Restart
- Install wizard with live log streaming
- Configuration form (collateral TXID, ZelID, public key)

**Network Stability**
- Loose reverse-path filtering (`rp_filter=2`) for correct P2P peer routing through NAT

**Reliability**
- P2SH compatibility patch script (`harbouros-flux-patch.sh`) retained as emergency fallback for environments where `insightexplorer=1` cannot be used
- Patch script clearly labelled as legacy/emergency-use-only

### Bug Fixes

- **System Updates**: Fixed "Install Updates" button silently failing — the `harbouros` service user was calling `sudo bash -c "apt-get update && apt-get upgrade"` but sudoers only permitted `sudo apt-get update` and `sudo apt-get upgrade` separately. Fixed by splitting into two subprocess calls.

### Infrastructure

- `apply-update.sh` now deploys Flux sudoers, install script, and patch script on every update
- `.gitignore` hardened to exclude `wallet.dat`, `flux.conf`, `fluxnode.conf`, `*.dat`, `*.ldb`, `*.sst`, `migration-backup-*/`

---

## v1.0.8 — UI Polish (2026-03-24)

- Ring gauge visualisations for CPU, RAM, and disk stats
- Fira Sans / Fira Code font pairing
- Blue gradient colour scheme for ring gauges
- Faster system stats polling (3s interval)
- System modal refreshes rings on open
- Plex certificate cache cleared after version upgrade to fix remote access stall

## v1.0.7 — Plex & Stability

- Plex remote access DNS fix
- Admin UI bug fixes

## v1.0.6 — Maintenance

- Internal improvements

## v1.0.5 — Non-root Service User

- Admin UI runs as dedicated `harbouros` system user (no longer root)
- Sudoers file for targeted privilege escalation

## v1.0.4 — Episode Database

- MySQL-backed episode database on harbouros.eu
- Pi queries API for show data instead of downloading full DB

## v1.0.3 — Security Hardening

- fail2ban SSH jail
- sysctl network hardening
- SSH X11Forwarding disabled

## v1.0.2 — Logrotate & fail2ban

- fail2ban installation migration
- Plex log rotation

## v1.0.1 — Initial Release

- Flask admin UI on port 8080
- Plex Media Server management
- NAS mount management
- System statistics
- Automatic Plex update timer
- HarbourOS self-update from GitHub
