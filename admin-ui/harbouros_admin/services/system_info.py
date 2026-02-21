"""System information service — CPU, RAM, temp, disk, uptime, logs, services, updates."""

import json
import os
import subprocess
import time

import psutil

PLEX_UPDATE_LOG = "/var/log/harbouros-plex-update.log"

MONITORED_SERVICES = [
    "plexmediaserver",
    "harbouros",
    "nftables",
    "avahi-daemon",
    "sshd",
]


def _run(cmd, timeout=30):
    """Run a command and return the CompletedProcess."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_run(cmd)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


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
                "2025-01-01T00:00:05+00:00 harbouros nftables[30]: Firewall rules loaded\n"
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


def check_updates():
    """Check for available apt package updates."""
    result = _run(["apt", "list", "--upgradable"], timeout=60)
    if result.returncode == 0:
        lines = [
            line for line in result.stdout.strip().split("\n")
            if "/" in line and "upgradable" in line.lower()
        ]
        return {"available": len(lines), "packages": lines}
    return {"available": 0, "packages": []}


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
