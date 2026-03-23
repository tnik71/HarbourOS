"""System information service — CPU, RAM, temp, disk, uptime, logs, services, updates."""

import json
import logging
import os
import subprocess
import time

import psutil

log = logging.getLogger(__name__)

PLEX_UPDATE_LOG = "/var/log/harbouros-plex-update.log"
HARBOUROS_UPDATE_STATUS = "/var/lib/harbouros/update-status.json"
HARBOUROS_UPDATE_LOG = "/var/log/harbouros-self-update.log"

_VERSION_PATHS = [
    "/opt/harbouros/repo/VERSION",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "VERSION"),
]


def _get_version_from_file():
    """Read the version from the VERSION file (works in prod and dev)."""
    for path in _VERSION_PATHS:
        try:
            with open(path) as f:
                return f.read().strip()
        except FileNotFoundError:
            continue
    return "unknown"

MONITORED_SERVICES = [
    "plexmediaserver",
    "harbouros",
    "avahi-daemon",
    "sshd",
    "fail2ban",
]


from .utils import _sudo


def _run(cmd, timeout=30):
    """Run a command and return the CompletedProcess."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_run(cmd)
    return subprocess.run(_sudo(cmd), capture_output=True, text=True, timeout=timeout)


def _mock_run(cmd):
    """Return mock responses for dev mode."""

    class MockResult:
        def __init__(self, stdout="", stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    if "poweroff" in cmd_str or "reboot" in cmd_str:
        return MockResult(stdout="OK\n")
    if "journalctl" in cmd_str:
        return MockResult(
            stdout=(
                "2025-01-01T00:00:01+00:00 harbouros systemd[1]: Started HarbourOS Admin UI.\n"
                "2025-01-01T00:00:02+00:00 harbouros gunicorn[100]: Listening on 0.0.0.0:8080\n"
                "2025-01-01T00:00:03+00:00 harbouros plexmediaserver[200]: Plex Media Server starting\n"
                "2025-01-01T00:00:04+00:00 harbouros avahi-daemon[50]: Registering harbouros.local\n"
            )
        )
    if "is-active" in cmd_str:
        return MockResult(stdout="active\n")
    if "apt" in cmd_str and "upgradable" in cmd_str:
        return MockResult(
            stdout="Listing...\nlibssl3/stable 3.0.13-1 arm64 [upgradable from: 3.0.12-1]\n"
        )
    if "apt-get" in cmd_str:
        return MockResult(stdout="0 upgraded, 0 newly installed, 0 to remove.\n")
    if "lsblk" in cmd_str:
        return MockResult(
            stdout=json.dumps(
                {
                    "blockdevices": [
                        {
                            "name": "mmcblk0",
                            "size": "32G",
                            "model": "SD32G",
                            "serial": "0x00001234",
                        }
                    ]
                }
            )
        )
    return MockResult(stdout="OK\n")


def get_cpu_percent():
    """Return CPU usage percentage (averaged across all cores)."""
    return psutil.cpu_percent(interval=1)


def get_memory():
    """Return memory stats in MB."""
    mem = psutil.virtual_memory()
    return {
        "total_mb": round(mem.total / 1024 / 1024),
        "used_mb": round(mem.used / 1024 / 1024),
        "available_mb": round(mem.available / 1024 / 1024),
        "percent": mem.percent,
    }


def get_disk():
    """Return root filesystem disk stats."""
    disk = psutil.disk_usage("/")
    return {
        "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
        "used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
        "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        "percent": disk.percent,
    }


def get_temperature():
    """Return CPU temperature in Celsius. Returns None if unavailable."""
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(thermal_path) as f:
            return round(int(f.read().strip()) / 1000, 1)
    except (FileNotFoundError, ValueError):
        return None


def get_uptime():
    """Return system uptime as a human-readable string and seconds."""
    boot_time = psutil.boot_time()
    uptime_secs = int(time.time() - boot_time)
    days = uptime_secs // 86400
    hours = (uptime_secs % 86400) // 3600
    minutes = (uptime_secs % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")

    return {
        "seconds": uptime_secs,
        "formatted": " ".join(parts),
    }


def get_system_status():
    """Return complete system status."""
    return {
        "cpu_percent": get_cpu_percent(),
        "memory": get_memory(),
        "disk": get_disk(),
        "temperature": get_temperature(),
        "uptime": get_uptime(),
    }


def power_action(action):
    """Execute shutdown or reboot."""
    if action not in ("shutdown", "reboot"):
        return False, f"Unknown power action: {action}"
    cmd_map = {
        "shutdown": ["systemctl", "poweroff"],
        "reboot": ["systemctl", "reboot"],
    }
    if os.environ.get("HARBOUROS_DEV"):
        return True, f"System would {action} (dev mode)"
    result = _run(cmd_map[action])
    if result.returncode == 0:
        return True, f"System {action} initiated"
    return False, result.stderr.strip()


def get_system_logs(service="all", lines=100):
    """Read system logs from journalctl."""
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "-o", "short-iso"]
    if service and service != "all":
        cmd.extend(["-u", service])
    result = _run(cmd)
    if result.returncode == 0:
        return result.stdout.strip().split("\n")
    return []


def get_service_statuses():
    """Get running/stopped status for key system services."""
    statuses = []
    for svc in MONITORED_SERVICES:
        result = _run(["systemctl", "is-active", svc])
        statuses.append({
            "name": svc,
            "active": result.stdout.strip() == "active",
        })
    return statuses


_update_cache = {"result": None, "ts": 0}
_UPDATE_CACHE_TTL = 3600  # re-run apt at most once per hour


def check_updates():
    """Check for available apt package updates (cached, 1h TTL)."""
    now = time.time()
    if _update_cache["result"] is not None and now - _update_cache["ts"] < _UPDATE_CACHE_TTL:
        return _update_cache["result"]
    result = _run(["apt", "list", "--upgradable"], timeout=60)
    if result.returncode == 0:
        lines = [
            line for line in result.stdout.strip().split("\n")
            if "/" in line and "upgradable" in line.lower()
        ]
        data = {"available": len(lines), "packages": lines}
    else:
        data = {"available": 0, "packages": []}
    _update_cache["result"] = data
    _update_cache["ts"] = now
    return data


def run_update():
    """Run apt-get update && apt-get upgrade -y. Returns log output."""
    result = _run(
        ["bash", "-c", "apt-get update -qq && apt-get upgrade -y"],
        timeout=600,
    )
    success = result.returncode == 0
    output = result.stdout if success else result.stdout + "\n" + result.stderr
    return success, output.strip()


def get_disk_details():
    """Return per-partition disk usage and SD card info."""
    partitions = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            partitions.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": round(usage.total / 1024**3, 1),
                "used_gb": round(usage.used / 1024**3, 1),
                "free_gb": round(usage.free / 1024**3, 1),
                "percent": usage.percent,
            })
        except (PermissionError, OSError):
            continue

    sd_info = None
    result = _run(["lsblk", "-J", "-o", "NAME,SIZE,MODEL,SERIAL", "-d"])
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            for dev in data.get("blockdevices", []):
                if dev["name"].startswith("mmcblk"):
                    sd_info = {
                        "name": dev["name"],
                        "size": dev.get("size"),
                        "model": dev.get("model"),
                        "serial": dev.get("serial"),
                    }
                    break
        except (json.JSONDecodeError, KeyError):
            pass

    # Add disk health warnings
    for p in partitions:
        if p["percent"] >= 90:
            p["warning"] = "critical"
        elif p["percent"] >= 80:
            p["warning"] = "warning"
        else:
            p["warning"] = None

    # Flag SD card as root disk so the UI can warn about SD wear
    if sd_info:
        root_device = next(
            (p["device"] for p in partitions if p["mountpoint"] == "/"), ""
        )
        sd_info["is_root"] = sd_info["name"] in root_device

    return {"partitions": partitions, "sd_card": sd_info}


def get_plex_update_log():
    """Read the Plex auto-update log file."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            "2025-01-01 01:00:00 Checking for Plex updates...",
            "2025-01-01 01:00:05 Plex is up to date (1.41.3.9314). No action needed.",
            "2025-01-07 01:00:00 Checking for Plex updates...",
            "2025-01-07 01:00:08 Updated Plex: 1.41.3.9314 -> 1.41.4.9400",
            "2025-01-07 01:00:10 Plex restarted.",
        ]
    try:
        with open(PLEX_UPDATE_LOG) as f:
            return f.read().strip().split("\n")
    except FileNotFoundError:
        return ["No update log found."]


def get_harbouros_update_status():
    """Read the HarbourOS self-update status file."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "update_available": False,
            "current_version": _get_version_from_file(),
            "current_sha": "abc1234",
            "last_check": "2025-06-15T01:00:00+00:00",
        }
    try:
        with open(HARBOUROS_UPDATE_STATUS) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "update_available": False,
            "current_version": _get_version_from_file(),
            "current_sha": "unknown",
            "last_check": None,
        }


def check_harbouros_update():
    """Run a fresh check against GitHub (check-only, no apply)."""
    if os.environ.get("HARBOUROS_DEV"):
        return get_harbouros_update_status()
    _run(["/usr/local/bin/harbouros-self-update.sh", "--check-only"], timeout=60)
    return get_harbouros_update_status()


def trigger_harbouros_update_check():
    """Manually trigger the HarbourOS update check."""
    if os.environ.get("HARBOUROS_DEV"):
        return True, "Update check triggered (dev mode)"
    result = _run(
        ["/usr/local/bin/harbouros-self-update.sh"],
        timeout=300,
    )
    success = result.returncode == 0
    if success:
        output = result.stdout.strip() or "Update completed successfully"
    else:
        # Script redirects all output to log file, so stderr is empty.
        # Read the last few lines from the log for a meaningful error message.
        try:
            with open(HARBOUROS_UPDATE_LOG) as f:
                lines = f.read().strip().split("\n")
                output = "\n".join(lines[-5:])
        except FileNotFoundError:
            output = result.stderr.strip() or "Update failed (no log available)"
    return success, output


def get_harbouros_update_log():
    """Read the HarbourOS self-update log file."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            "2025-06-15 01:00:00 Checking for HarbourOS updates...",
            "2025-06-15 01:00:02 HarbourOS is up to date (1.0.0, abc1234). No action needed.",
        ]
    try:
        with open(HARBOUROS_UPDATE_LOG) as f:
            return f.read().strip().split("\n")
    except FileNotFoundError:
        return ["No update log found."]


def get_security_status(failed_login_count=0):
    """Return the current security posture of the system."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "password_changed": True,
            "fail2ban_active": True,
            "root_login_disabled": True,
            "password_auth_enabled": True,
            "fail2ban_banned": 0,
            "failed_logins_session": failed_login_count,
        }

    from .auth_service import is_password_changed

    # fail2ban active?
    f2b_active = _run(["systemctl", "is-active", "fail2ban"]).stdout.strip() == "active"

    # SSH: PermitRootLogin no
    root_login_disabled = False
    try:
        with open("/etc/ssh/sshd_config") as f:
            content = f.read()
            root_login_disabled = "PermitRootLogin no" in content
    except OSError:
        pass

    # SSH: PasswordAuthentication
    pw_auth_enabled = True
    try:
        with open("/etc/ssh/sshd_config") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("PasswordAuthentication"):
                    pw_auth_enabled = "yes" in stripped.lower()
                    break
    except OSError:
        pass

    # fail2ban banned count (best-effort)
    banned_count = 0
    try:
        result = subprocess.run(
            _sudo(["fail2ban-client", "status", "sshd"]),
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "Currently banned" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    banned_count = int(parts[-1].strip())
                    break
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass

    return {
        "password_changed": is_password_changed(),
        "fail2ban_active": f2b_active,
        "root_login_disabled": root_login_disabled,
        "password_auth_enabled": pw_auth_enabled,
        "fail2ban_banned": banned_count,
        "failed_logins_session": failed_login_count,
    }


def get_setup_checks():
    """Return a set of readiness checks for the setup wizard."""
    if os.environ.get("HARBOUROS_DEV"):
        return {
            "plex_reachable": True,
            "static_ip": False,
            "temperature_ok": True,
            "temperature_c": 52.0,
            "nas_count": 1,
        }

    from . import mount_manager, network_manager

    # Plex reachability
    plex_reachable = False
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:32400/identity", timeout=3)
        plex_reachable = True
    except Exception:
        pass

    # Static IP
    static_ip = network_manager.get_ip_mode() == "static"

    # Temperature
    temp = get_temperature()
    temp_ok = temp is None or temp < 70

    # NAS mounts
    try:
        mounts = mount_manager.list_mounts()
        nas_count = len(mounts)
    except Exception:
        nas_count = 0

    return {
        "plex_reachable": plex_reachable,
        "static_ip": static_ip,
        "temperature_ok": temp_ok,
        "temperature_c": temp,
        "nas_count": nas_count,
    }
