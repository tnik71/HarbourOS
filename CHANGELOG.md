# HarbourOS Changelog

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
