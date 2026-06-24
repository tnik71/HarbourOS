# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Local development (sets HARBOUROS_DEV=1, uses temp paths for all config)
make dev                    # creates venv, installs deps, starts Flask on :8080

# Manual equivalent
source admin-ui/venv/bin/activate
cd admin-ui && HARBOUROS_DEV=1 python -m flask --app harbouros_admin.app run --host 0.0.0.0 --port 8080 --debug

# Tests
make test
cd admin-ui && venv/bin/python -m pytest tests/ -v
cd admin-ui && venv/bin/python -m pytest tests/test_app.py::test_api_plex_status -v  # single test

# Deploy to Pi
make deploy PI=192.168.1.88       # default PI=harbouros.local
./deploy.sh 192.168.1.88 tnik71   # explicit user
```

## Architecture

### Repository layout

| Path | Purpose |
|---|---|
| `admin-ui/harbouros_admin/` | Flask application (production code) |
| `config/` | systemd units, shell scripts, sudoers files — deployed to the Pi |
| `scripts/` | One-shot Pi scripts (apply-update, migrate-plex, uninstall) |
| `stage-harbouros/` | pi-gen stages for building the OS image |
| `deploy.sh` | rsync → `/tmp/harbouros-deploy/` then SSH to run `apply-update.sh` |

### Flask application (`admin-ui/harbouros_admin/`)

Single-module Flask app created by `create_app()` in `app.py`. All routes live in that file — there are no Blueprints. The app runs as gunicorn on port 8080 under the `harbouros` system user in production.

**Middleware applied to every request:**
- `csrf_check()` — compares Origin/Referer host to `request.host` for non-GET requests
- `login_required` decorator — redirects to `/setup` if setup flag missing, else to `/login`
- `set_security_headers()` — adds CSP, X-Frame-Options, X-Content-Type-Options

**Setup flag:** `/etc/harbouros/.setup-complete` (or `$TMPDIR/harbouros-setup-complete` in dev). Before this file exists, only endpoints listed in `_SETUP_ENDPOINTS` are accessible.

### Service layer (`services/`)

Each service module owns a domain and is imported directly in `app.py`. They do not cross-import each other, except `episodes_service` which imports `plex_service` to query the local Plex library.

| Module | Domain |
|---|---|
| `auth_service.py` | bcrypt password hash in `/etc/harbouros/admin.json`; session secret key |
| `plex_service.py` | Plex systemd control + Plex HTTP API (`:32400`); 30s status cache |
| `flux_service.py` | FluxOS/zelcash control; FluxOS REST API (`:16127`); benchmark; wallet |
| `system_info.py` | CPU/RAM/temp via psutil; journald logs; HarbourOS self-update |
| `mount_manager.py` | NAS mount CRUD → generates systemd `.mount`/`.automount` units |
| `network_manager.py` | hostname, DHCP/static IP via `dhcpcd.conf` |
| `episodes_service.py` | Missing-episode tracker: queries `harbouros.eu/db/api.php`, compares against Plex |
| `backup_service.py` | tar.gz of `/etc/harbouros/` config |
| `utils.py` | `_sudo(cmd)` — prepends `sudo` when not root and not in dev mode |

### Dev mode (`HARBOUROS_DEV=1`)

Every service module checks `os.environ.get("HARBOUROS_DEV")` and redirects:
- File paths to `$TMPDIR/harbouros-dev/` (config, mounts, auth)
- `subprocess` calls to `_mock_run()` functions that return canned responses
- Setup flag to `$TMPDIR/harbouros-setup-complete`

Tests always set `HARBOUROS_DEV=1` (in `conftest.py`). The `conftest.py` also pre-authenticates the `client` fixture via `session_transaction`.

### Deploy pipeline

`deploy.sh` rsyncs three things to `/tmp/harbouros-deploy/` on the Pi:
1. `admin-ui/harbouros_admin/` → installs to `/opt/harbouros/harbouros_admin/`
2. `config/` → systemd units, sudoers, shell scripts
3. `scripts/apply-update.sh` → executed on Pi as root

`apply-update.sh` applies versioned one-time migrations (flagged in `/etc/harbouros/.migration-X.X.X`), updates the venv, copies files, reloads systemd, and restarts `harbouros.service`. **`git pull` on the Pi does NOT update the running app** — `deploy.sh` must be run.

### On-Pi runtime paths

| Path | Contents |
|---|---|
| `/opt/harbouros/harbouros_admin/` | Running Flask app (rsynced, not a git clone) |
| `/opt/harbouros/repo/` | Git clone (used only for version reads and self-update) |
| `/opt/harbouros/venv/` | Python virtualenv |
| `/etc/harbouros/` | Runtime config: `admin.json`, `flux.json`, `mounts.json` |
| `/var/log/harbouros-*.log` | Update and install logs |

### Flux node integration

`flux_service.py` calls the FluxOS REST API at `http://127.0.0.1:16127` for node status, benchmark results, and wallet data. The fluxd daemon (`zelcash.service`) stores its config at `/var/lib/fluxd/flux.conf` and is managed separately from FluxOS (which runs under root pm2 at `/opt/flux/`). The `harbouros` Flask app has no direct access to the pm2 or root-owned FluxOS process — it reads state via the FluxOS HTTP API only.

### Flux + Pi operational notes

- FluxOS and watchdog run under **root pm2** (`sudo PM2_HOME=/root/.pm2 pm2 jlist`) — not the `tnik71` user pm2
- `/opt/flux/certs/v1.key` must be `root:tnik71 640` for the FluxOS process to read it
- `zelflux_update: '1'` in `/root/watchdog/config.js` enables FluxOS auto-updates via the watchdog
- `zelcash_update` and `zelbench_update` are left `'0'` (manual operator approval required for daemon updates)
