# HarbourOS

A custom Raspberry Pi OS image that turns a Raspberry Pi 5 into a dedicated Plex Media Server appliance with a web-based admin UI.

## Features

- Web admin dashboard (CasaOS-style desktop UI) on port 8080
- Plex Media Server management (start/stop/restart, logs, auto-update)
- NAS mount management (NFS/SMB) with network device discovery
- System monitoring (CPU, RAM, disk, temperature, services)
- Network configuration (hostname, DHCP/static IP)
- First-boot setup wizard
- Episode Manager — find missing TV episodes against 21,000+ shows database
- Session-based authentication with bcrypt password hashing
- Docker Plex migration tool (preserves libraries, watch history, metadata)
- Security hardening (CSRF protection, non-root service, rate limiting, security headers)
- **Flux CUMULUS node support** — deploy, monitor, and manage a Flux node alongside Plex

## Architecture

```
Flask + Gunicorn (:8080)  →  6 service modules  →  systemctl / psutil / config files

Templates: base.html → dashboard.html (SPA with modals), login.html, setup.html
Static:    app.js, style.css
Tests:     89 (test_app.py, test_auth_service.py, test_mount_manager.py)
Build:     pi-gen stages → Raspberry Pi OS image
```

## Development

```bash
# Set up local dev environment
make setup-dev

# Run Flask dev server on http://localhost:8080
make dev

# Run tests
make test
```

Default password: `harbouros`

Dev mode (`HARBOUROS_DEV=1`) mocks all system calls (systemctl, mount, etc.) so the admin UI runs on macOS/Linux without a Raspberry Pi.

## Building the Image

```bash
make build
```

Builds a Raspberry Pi OS image using pi-gen + Docker. Output goes to `output/`.

## Remote Install (No SD Card Needed)

Install HarbourOS directly onto a running Raspberry Pi over SSH — no image flashing required:

```bash
make install-remote PI=192.168.1.50   # install via IP
make install-remote PI=raspberrypi.local  # install via hostname
```

This connects to the Pi, installs all packages (Plex, etc.), deploys the admin UI, and starts services. The Pi must be running Raspberry Pi OS with SSH enabled.

## Flux Node

HarbourOS supports running a Flux CUMULUS node alongside Plex on the same Raspberry Pi 5.

**Recommended hardware:** Raspberry Pi 5 (8 GB RAM) + NVMe SSD (250 GB+) via PCIe adapter.

**Features:**
- Flux node installer with pre-flight hardware checks
- Node status monitoring (CONFIRMED / STARTED / EXPIRED / OFFLINE)
- Benchmark results: CPU cores, RAM, disk speed, EPS, download/upload
- Wallet balance and reward tracking
- Docker container count and Explorer sync progress
- Node action buttons: Start, Stop, Restart
- Live install log streaming

**Insight Explorer mode** (`insightexplorer=1`) is the standard deployment configuration. It eliminates FluxOS P2SH transaction crashes without requiring source patching.

**Flux + Plex coexistence:** Both services run concurrently. Plex and fluxd are managed as separate systemd services. See `config/harbouros-flux.service` for the fluxd unit template.

> **Note:** `harbouros-flux.service` is not auto-deployed by `apply-update.sh`. Updating the Flux daemon service definition requires manual operator action to avoid interrupting block sync.

## Migrating from Docker Plex

If you're running Plex in Docker (e.g., via CasaOS or docker-compose), HarbourOS can migrate it to a native install while preserving all your libraries, watch history, and metadata:

```bash
make migrate-plex PI=192.168.1.50
```

The script auto-detects your Docker Plex container, backs up the data, installs native Plex, and restores everything. Use `--dry-run` to preview without making changes.

## Deploying Updates

Push code changes to a running Pi without rebuilding the image:

```bash
make deploy              # deploy to harbouros.local
make deploy PI=10.0.0.5  # deploy to a specific IP
```

This syncs admin UI code, config files, and scripts to the Pi, installs any new dependencies, and restarts services as needed. User data (passwords, mount configs) is never touched.

## Project Structure

```
admin-ui/               Flask application
  harbouros_admin/
    app.py              Routes and API endpoints
    services/           Backend service modules
      auth_service.py   Authentication and password management
      mount_manager.py  NAS mount CRUD and systemd unit generation
      network_manager.py Hostname and IP configuration
      plex_service.py   Plex Media Server control
      flux_service.py   Flux node control, status, benchmarks, wallet
      episodes_service.py Episode Manager — missing episode detection
      system_info.py    System status, logs, updates, disk info
    templates/          Jinja2 templates
    static/             CSS, JS, images
  tests/                pytest test suite
config/                 systemd services, Plex update script
scripts/                Deploy and install scripts
stage-harbouros/           pi-gen build stages
```
