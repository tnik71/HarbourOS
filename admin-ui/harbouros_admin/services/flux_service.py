"""Flux Node service management for HarbourOS."""

import json
import os
import subprocess
import time
import urllib.request

from .utils import _sudo

FLUX_CONFIG_PATH = "/etc/harbouros/flux.json"
FLUX_BENCHMARK_PATH = "/etc/harbouros/flux-benchmark.json"
FLUX_INSTALL_LOG = "/var/log/harbouros-flux-install.log"

FLUXD_SERVICE = "zelcash"  # Official FluxOS daemon service name
FLUXOS_API_URL = "http://127.0.0.1:16127"  # FluxOS HTTP API

_DEFAULT_CONFIG = {
    "collateral_txid": "",
    "collateral_index": "0",
    "zelid": "",
    "public_key": "",
    "api_port": 16127,
    "installed": False,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run(cmd, timeout=30):
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_run(cmd)
    return subprocess.run(
        _sudo(cmd), capture_output=True, text=True, timeout=timeout
    )


def _mock_run(cmd):
    class MockResult:
        def __init__(self, stdout="", stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    if "is-active" in cmd_str and "zelcash" in cmd_str:
        return MockResult(stdout="active\n")
    if "is-active" in cmd_str and "docker" in cmd_str:
        return MockResult(stdout="active\n")
    if "docker" in cmd_str and "ps" in cmd_str:
        # One JSON object per line (JSONL format, matching docker ps --format output)
        lines = [
            '{"id":"a1b2c3d4","image":"runonflux/website:latest","status":"Up 2 hours","name":"flux_website_1"}',
            '{"id":"b2c3d4e5","image":"runonflux/api:latest","status":"Up 2 hours","name":"flux_api_1"}',
            '{"id":"c3d4e5f6","image":"runonflux/syncthing:latest","status":"Up 2 hours","name":"flux_syncthing_1"}',
        ]
        return MockResult(stdout="\n".join(lines))
    if "journalctl" in cmd_str:
        return MockResult(stdout=(
            "May 08 10:00:01 harbouros zelcash[1234]: Zelnode status: ENABLED\n"
            "May 08 10:00:05 harbouros zelcash[1234]: Block height: 1823045\n"
            "May 08 10:00:10 harbouros zelcash[1234]: Connected peers: 8\n"
        ))
    if "systemctl" in cmd_str:
        return MockResult(stdout="OK\n")
    return MockResult(stdout="OK\n")


def _load_config():
    try:
        with open(FLUX_CONFIG_PATH) as f:
            cfg = json.load(f)
        # Fill in any missing keys from defaults
        for k, v in _DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULT_CONFIG)


def _save_config(cfg):
    os.makedirs(os.path.dirname(FLUX_CONFIG_PATH), exist_ok=True)
    with open(FLUX_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Status cache
# ---------------------------------------------------------------------------

_status_cache = {"result": None, "ts": 0}
_STATUS_CACHE_TTL = 30

_network_cache = {"result": None, "ts": 0}
_NETWORK_CACHE_TTL = 300  # 5 minutes — public API, no need to hammer it

_wallet_cache = {"result": None, "ts": 0}
_WALLET_CACHE_TTL = 300  # 5 minutes

# Flux block reward economics (Cumulus tier)
# 75% of block reward goes to nodes; Cumulus gets 1/3 of that
# Block time ~2 min → 720 blocks/day
_BLOCKS_PER_DAY = 720
_CUMULUS_REWARD_FRACTION = 0.75 / 3   # 25% of total block reward
_NETWORK_BLOCK_HEIGHT = 2_580_000     # approximate, updated from network


def _invalidate_status_cache():
    _status_cache["result"] = None
    _status_cache["ts"] = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_config():
    """Return current Flux node configuration."""
    return _load_config()


def save_config(data):
    """Save Flux node configuration. Returns (success, message)."""
    allowed = {"collateral_txid", "collateral_index", "zelid", "public_key", "api_port"}
    cfg = _load_config()
    for key in allowed:
        if key in data:
            cfg[key] = data[key]
    try:
        _save_config(cfg)
        return True, "Configuration saved"
    except OSError as e:
        return False, str(e)


def get_status():
    """Get Flux node status (cached, 30s TTL)."""
    now = time.time()
    if _status_cache["result"] is not None and now - _status_cache["ts"] < _STATUS_CACHE_TTL:
        return _status_cache["result"]

    cfg = _load_config()

    # Check if fluxd daemon is running
    daemon_result = _run(["systemctl", "is-active", FLUXD_SERVICE])
    running = daemon_result.stdout.strip() == "active"

    # Check if Docker is running
    docker_result = _run(["systemctl", "is-active", "docker"])
    docker_running = docker_result.stdout.strip() == "active"

    # Count active Docker containers
    containers = []
    if docker_running:
        docker_ps = _run(["docker", "ps", "--format", "{{json .}}"])
        if docker_ps.returncode == 0 and docker_ps.stdout.strip():
            for line in docker_ps.stdout.strip().splitlines():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Query fluxd RPC for node status (only if running and not in dev mode)
    node_status = None
    block_height = None
    version = None

    if running and not os.environ.get("HARBOUROS_DEV"):
        node_status, block_height, version = _query_fluxos_api()
    elif os.environ.get("HARBOUROS_DEV"):
        node_status = "ENABLED"
        block_height = 1823045
        version = "5.5.0"

    # Calculate uptime
    uptime_seconds = None
    if running:
        ts_result = _run([
            "systemctl", "show", FLUXD_SERVICE,
            "--property=ActiveEnterTimestamp"
        ])
        if ts_result.returncode == 0:
            uptime_seconds = ts_result.stdout.strip().replace("ActiveEnterTimestamp=", "")

    # Consider installed if config says so, or if fluxd is actually running
    installed = cfg.get("installed", False) or running

    # Fetch live network height for accurate sync percentage
    network_height = _NETWORK_BLOCK_HEIGHT
    try:
        req = urllib.request.Request(
            "https://api.runonflux.io/daemon/getinfo",
            headers={"User-Agent": "HarbourOS/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode())
            if d.get("status") == "success":
                network_height = d["data"].get("blocks", network_height)
    except Exception:
        pass

    result = {
        "installed": installed,
        "running": running,
        "version": version,
        "node_status": node_status,
        "block_height": block_height,
        "network_height": network_height,
        "docker_running": docker_running,
        "containers": len(containers),
        "container_list": containers,
        "api_port": cfg.get("api_port", 16127),
        "uptime": uptime_seconds,
        "error": None,
    }

    _status_cache["result"] = result
    _status_cache["ts"] = now
    return result


def _get_network_stats():
    """Fetch Flux network node counts from public API (5-min cache)."""
    now = time.time()
    if _network_cache["result"] is not None and now - _network_cache["ts"] < _NETWORK_CACHE_TTL:
        return _network_cache["result"]
    try:
        req = urllib.request.Request(
            "https://api.runonflux.io/daemon/getzelnodecount",
            headers={"User-Agent": "HarbourOS/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                _network_cache["result"] = data["data"]
                _network_cache["ts"] = now
                return data["data"]
    except Exception:
        pass
    return _network_cache["result"]  # return stale if fetch fails


def get_widget_data():
    """Return compact Flux node data for the dashboard widget."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "running": True,
            "node_status": "ENABLED",
            "block_height": 1823045,
            "network_height": 2580000,
            "sync_pct": 100.0,
            "cumulus_nodes": 4086,
            "est_daily_flux": 3.14,
            "version": "8.12.0",
        }

    status = get_status()
    net = _get_network_stats()

    network_height = _NETWORK_BLOCK_HEIGHT
    # Use live network height if we have it
    try:
        req = urllib.request.Request(
            "https://api.runonflux.io/daemon/getinfo",
            headers={"User-Agent": "HarbourOS/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode())
            if d.get("status") == "success":
                network_height = d["data"].get("blocks", network_height)
    except Exception:
        pass

    block_height = status.get("block_height") or 0
    sync_pct = round(min(100.0, block_height / network_height * 100), 1) if network_height else None

    cumulus_nodes = None
    est_daily = None
    if net:
        cumulus_nodes = net.get("cumulus-enabled")
        if cumulus_nodes and cumulus_nodes > 0:
            # Block reward = 18.75 FLUX; 75% to nodes; Cumulus = 1/3 of that
            reward_per_block = 18.75 * _CUMULUS_REWARD_FRACTION / cumulus_nodes
            est_daily = round(reward_per_block * _BLOCKS_PER_DAY, 2)

    return {
        "running": status.get("running", False),
        "node_status": status.get("node_status"),
        "block_height": block_height,
        "network_height": network_height,
        "sync_pct": sync_pct,
        "cumulus_nodes": cumulus_nodes,
        "est_daily_flux": est_daily,
        "version": status.get("version"),
    }


def get_wallet_data():
    """Return wallet balance and earnings for the configured ZelID address."""
    import datetime

    if os.environ.get("HARBOUROS_DEV"):
        return {
            "balance": 1080.83,
            "earned_today": 0.83,
            "earned_total": 0.83,
            "last_payout": "2026-05-09 14:32",
            "payout_count": 1,
        }

    now = time.time()
    if _wallet_cache["result"] is not None and now - _wallet_cache["ts"] < _WALLET_CACHE_TTL:
        return _wallet_cache["result"]

    cfg = _load_config()
    zelid = cfg.get("zelid", "").strip()
    if not zelid:
        return None

    explorer = "https://explorer.runonflux.io/api"
    result = {"balance": None, "earned_today": None, "earned_total": None,
              "last_payout": None, "payout_count": 0}

    # Fetch address summary
    try:
        req = urllib.request.Request(
            f"{explorer}/addr/{zelid}",
            headers={"User-Agent": "HarbourOS/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            addr = json.loads(resp.read().decode())
            result["balance"] = addr.get("balance")
            total_received = addr.get("totalReceived") or 0
    except Exception:
        return result

    # Fetch transaction history (page 0 = most recent)
    try:
        req = urllib.request.Request(
            f"{explorer}/txs?address={zelid}&pageNum=0",
            headers={"User-Agent": "HarbourOS/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            tx_data = json.loads(resp.read().decode())
            txs = tx_data.get("txs", [])
    except Exception:
        txs = []

    # Filter to reward txs only — rewards are small (Cumulus ~0.83 FLUX, never > 5 FLUX)
    # Exclude the collateral TX itself and any vout >= 10 FLUX (change/collateral outputs)
    collateral_txid = cfg.get("collateral_txid", "").strip()
    cutoff_24h = now - 86400
    earned_today = 0.0
    earned_total = 0.0
    last_payout_ts = None
    payout_count = 0

    for tx in txs:
        tx_time = tx.get("time", 0)
        # Skip the collateral TX entirely
        if collateral_txid and tx.get("txid", "") == collateral_txid:
            continue
        # Sum vout values going to our address that look like reward amounts (< 10 FLUX)
        incoming = sum(
            float(v.get("value", 0))
            for v in tx.get("vout", [])
            if zelid in (v.get("scriptPubKey") or {}).get("addresses", [])
            and float(v.get("value", 0)) < 10  # rewards are < 10 FLUX; collateral/change are much larger
        )
        if incoming > 0:
            payout_count += 1
            earned_total += incoming
            if tx_time >= cutoff_24h:
                earned_today += incoming
            if last_payout_ts is None:
                last_payout_ts = tx_time

    result["earned_today"] = round(earned_today, 4) if payout_count > 0 else None
    result["earned_total"] = round(earned_total, 4) if payout_count > 0 else None
    result["payout_count"] = payout_count
    if last_payout_ts:
        result["last_payout"] = datetime.datetime.fromtimestamp(last_payout_ts).strftime("%Y-%m-%d %H:%M")

    _wallet_cache["result"] = result
    _wallet_cache["ts"] = now
    return result


def _query_fluxos_api():
    """Query the FluxOS HTTP API for node status, block height, and version."""
    node_status = None
    block_height = None
    version = None

    # FluxOS version
    try:
        with urllib.request.urlopen(f"{FLUXOS_API_URL}/flux/version", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                version = data.get("data")
    except Exception:
        pass

    # Daemon info (block height)
    try:
        with urllib.request.urlopen(f"{FLUXOS_API_URL}/daemon/getinfo", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                block_height = data["data"].get("blocks")
    except Exception:
        pass

    # Node status (only meaningful after collateral confirmed)
    try:
        with urllib.request.urlopen(f"{FLUXOS_API_URL}/daemon/getfluxnodestatus", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                node_status = data["data"].get("status")
    except Exception:
        pass

    return node_status, block_height, version


def action(name):
    """Perform a named action: start, stop, restart."""
    actions = {
        "start": lambda: _run(["systemctl", "start", FLUXD_SERVICE]),
        "stop": lambda: _run(["systemctl", "stop", FLUXD_SERVICE]),
        "restart": lambda: _run(["systemctl", "restart", FLUXD_SERVICE]),
    }
    fn = actions.get(name)
    if fn is None:
        return False, f"Unknown action: {name}"
    result = fn()
    _invalidate_status_cache()
    success = result.returncode == 0
    return success, "OK" if success else (result.stderr.strip() or f"Failed to {name} Flux node")


def get_logs(lines=80):
    """Return recent fluxd journal log lines."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            "May 08 10:00:00 harbouros zelcash[1234]: Zelnode status: ENABLED",
            "May 08 10:00:01 harbouros zelcash[1234]: Block height: 1823045",
            "May 08 10:00:05 harbouros zelcash[1234]: Connected peers: 8",
            "May 08 10:00:10 harbouros zelcash[1234]: Zelnode IP: 203.0.113.10:16125",
            "May 08 10:00:15 harbouros zelcash[1234]: Confirmed tier: CUMULUS",
        ]
    result = _run([
        "journalctl", "-u", FLUXD_SERVICE,
        "-n", str(lines),
        "--no-pager",
        "--output=short",
    ])
    if result.returncode == 0:
        return result.stdout.strip().splitlines()
    return []


def get_docker_status():
    """Return Docker daemon status and running containers."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "running": True,
            "containers": [
                {"id": "a1b2c3d4", "image": "runonflux/website:latest", "status": "Up 2 hours", "name": "flux_website_1"},
                {"id": "b2c3d4e5", "image": "runonflux/api:latest", "status": "Up 2 hours", "name": "flux_api_1"},
                {"id": "c3d4e5f6", "image": "runonflux/syncthing:latest", "status": "Up 2 hours", "name": "flux_syncthing_1"},
            ],
        }
    docker_result = _run(["systemctl", "is-active", "docker"])
    docker_running = docker_result.stdout.strip() == "active"

    containers = []
    if docker_running:
        ps_result = _run([
            "docker", "ps",
            "--format", '{"id":"{{.ID}}","image":"{{.Image}}","status":"{{.Status}}","name":"{{.Names}}"}',
        ])
        if ps_result.returncode == 0:
            for line in ps_result.stdout.strip().splitlines():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    return {"running": docker_running, "containers": containers}


def get_benchmark_status():
    """Return benchmark results from fluxbench-cli."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "ran_at": "2026-05-08T10:00:00",
            "cpu_cores": 4,
            "ram_gb": 8.0,
            "disk_write_mbps": 210.5,
            "network_mbps": 95.2,
            "passed": True,
            "tier": "CUMULUS",
            "status": "online",
            "details": "All checks passed. Node qualifies for Cumulus tier.",
        }
    # Query live from fluxbench-cli
    getstatus = _run(["fluxbench-cli", "-datadir=/var/lib/fluxbench", "getstatus"])
    getbench = _run(["fluxbench-cli", "-datadir=/var/lib/fluxbench", "getbenchmarks"])
    result = {"status": None, "passed": None, "tier": None,
              "cores": None, "ram_gb": None, "disk_write_mbps": None, "eps": None,
              "download_mbps": None, "upload_mbps": None,
              "ran_at": None, "details": None}
    if getstatus.returncode == 0:
        try:
            s = json.loads(getstatus.stdout.strip())
            result["status"] = s.get("status")
            result["tier"] = s.get("benchmarking") or s.get("tier") or s.get("zelnode_tier")
        except (json.JSONDecodeError, ValueError):
            pass
    if getbench.returncode == 0:
        try:
            b = json.loads(getbench.stdout.strip())
            result["cores"] = b.get("cores")
            result["ram_gb"] = b.get("ram")
            result["disk_write_mbps"] = b.get("ddwrite")
            result["eps"] = b.get("eps")
            result["download_mbps"] = b.get("download_speed")
            result["upload_mbps"] = b.get("upload_speed")
            ts = b.get("time")
            if ts:
                import datetime
                try:
                    result["ran_at"] = datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    result["ran_at"] = str(ts)
            error = b.get("error", "")
            result["passed"] = (b.get("status") not in (None, "failed", "running")) and (not error)
            result["details"] = error if error else None
        except (json.JSONDecodeError, ValueError):
            pass
    if result["status"] is None and result["ram_gb"] is None:
        return None
    return result


_ANSI_ESCAPE = None

def _strip_ansi(text):
    global _ANSI_ESCAPE
    if _ANSI_ESCAPE is None:
        import re
        _ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[mGKHF]|\x1b\[[0-9;]*m|\x1b\(B')
    return _ANSI_ESCAPE.sub('', text)


def get_install_log(lines=100):
    """Return recent lines from the install log, ANSI-stripped."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            "[OK] RAM check: 8.0 GB (minimum 7.5 GB)",
            "[OK] Docker installed",
            "[OK] FluxNode multitool completed",
            "[OK] zelcash service enabled",
            "Installation complete.",
        ]
    result = _run(["tail", "-n", str(lines), FLUX_INSTALL_LOG])
    if result.returncode == 0:
        return [_strip_ansi(l) for l in result.stdout.strip().splitlines() if _strip_ansi(l).strip()]
    return []


def start_install():
    """Kick off the background install script. Returns (success, message)."""
    if os.environ.get("HARBOUROS_DEV"):
        return True, "Install started (dev mode)"
    os.makedirs(os.path.dirname(FLUX_INSTALL_LOG), exist_ok=True)
    with open(FLUX_INSTALL_LOG, "w") as log_fh:
        result = subprocess.Popen(
            _sudo(["/usr/local/bin/harbouros-flux-install.sh"]),
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,
        )
    return True, f"Install started (pid {result.pid})"
