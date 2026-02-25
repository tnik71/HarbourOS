"""Plex Media Server service management via systemctl."""

import json
import os
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

SERVICE_NAME = "plexmediaserver"


def _sudo(cmd):
    """Prepend sudo to a command when running as non-root."""
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        return ["sudo"] + cmd
    return cmd


PLEX_LOG_DIR = (
    "/var/lib/plexmediaserver/Library/Application Support"
    "/Plex Media Server/Logs"
)
PLEX_PREFS_PATH = (
    "/var/lib/plexmediaserver/Library/Application Support"
    "/Plex Media Server/Preferences.xml"
)
PLEX_BASE_URL = "http://localhost:32400"


def _run(cmd, check=False):
    """Run a shell command and return the result."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_run(cmd)
    return subprocess.run(
        _sudo(cmd), capture_output=True, text=True, check=check, timeout=30
    )


def _mock_run(cmd):
    """Return mock responses for development mode."""

    class MockResult:
        def __init__(self, stdout="", stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    if "is-active" in cmd_str:
        return MockResult(stdout="active\n")
    if "show" in cmd_str and "ActiveEnterTimestamp" in cmd_str:
        return MockResult(stdout="ActiveEnterTimestamp=Thu 2025-01-01 00:00:00 UTC\n")
    if "dpkg-query" in cmd_str:
        return MockResult(stdout="1.41.3.9314-a0bfb8370\n")
    return MockResult(stdout="OK\n")


def get_status():
    """Get Plex service status."""
    result = _run(["systemctl", "is-active", SERVICE_NAME])
    running = result.stdout.strip() == "active"

    version = None
    version_result = _run([
        "dpkg-query", "-W", "-f=${Version}",
        "plexmediaserver"
    ])
    if version_result.returncode == 0:
        version = version_result.stdout.strip()

    uptime = None
    if running:
        ts_result = _run([
            "systemctl", "show", SERVICE_NAME,
            "--property=ActiveEnterTimestamp"
        ])
        if ts_result.returncode == 0:
            uptime = ts_result.stdout.strip().replace("ActiveEnterTimestamp=", "")

    return {
        "running": running,
        "version": version,
        "uptime": uptime,
    }


def start():
    """Start Plex Media Server."""
    result = _run(["systemctl", "start", SERVICE_NAME])
    return result.returncode == 0


def stop():
    """Stop Plex Media Server."""
    result = _run(["systemctl", "stop", SERVICE_NAME])
    return result.returncode == 0


def restart():
    """Restart Plex Media Server."""
    result = _run(["systemctl", "restart", SERVICE_NAME])
    return result.returncode == 0


def action(name):
    """Perform a named action (start/stop/restart)."""
    actions = {"start": start, "stop": stop, "restart": restart}
    fn = actions.get(name)
    if fn is None:
        return False, f"Unknown action: {name}"
    success = fn()
    return success, "OK" if success else f"Failed to {name} Plex"


def get_logs(lines=50):
    """Read recent Plex log lines."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            "[2025-01-01 00:00:00] Plex Media Server v1.41.3 starting...",
            "[2025-01-01 00:00:01] Listening on port 32400",
            "[2025-01-01 00:00:02] Library scan complete: 150 items",
        ]

    log_file = os.path.join(PLEX_LOG_DIR, "Plex Media Server.log")
    try:
        result = subprocess.run(
            _sudo(["tail", "-n", str(lines), log_file]),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def get_plex_token():
    """Read the X-Plex-Token from Plex Preferences.xml."""
    if os.environ.get("HARBOUROS_DEV"):
        return "dev-mock-token"
    try:
        tree = ET.parse(PLEX_PREFS_PATH)
        root = tree.getroot()
        return root.get("PlexOnlineToken")
    except (FileNotFoundError, ET.ParseError):
        return None


def _mock_libraries():
    """Return mock library data for dev mode."""
    return {
        "libraries": [
            {"key": "1", "title": "Movies", "type": "movie", "count": 245},
            {"key": "2", "title": "TV Shows", "type": "show", "count": 48},
            {"key": "3", "title": "Anime", "type": "show", "count": 156},
            {"key": "4", "title": "Music", "type": "artist", "count": 312},
        ],
        "recently_added": [
            {"title": "Dune: Part Two", "type": "movie", "added_at": 1706140800, "year": 2024, "library": "Movies", "thumb": None},
            {"title": "The Bear - S03E01", "type": "episode", "added_at": 1706054400, "year": 2024, "library": "TV Shows", "thumb": None},
            {"title": "Oppenheimer", "type": "movie", "added_at": 1705968000, "year": 2023, "library": "Movies", "thumb": None},
            {"title": "Killers of the Flower Moon", "type": "movie", "added_at": 1705881600, "year": 2023, "library": "Movies", "thumb": None},
            {"title": "Slow Horses - S03E06", "type": "episode", "added_at": 1705795200, "year": 2023, "library": "TV Shows", "thumb": None},
        ],
    }


def get_libraries():
    """Fetch Plex library sections and recently added items."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_libraries()

    token = get_plex_token()
    if not token:
        return {"libraries": [], "recently_added": [], "error": "No Plex token found"}

    headers = {
        "X-Plex-Token": token,
        "Accept": "application/json",
    }

    libraries = []
    try:
        req = urllib.request.Request(
            PLEX_BASE_URL + "/library/sections",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            for d in data.get("MediaContainer", {}).get("Directory", []):
                key = d.get("key")
                count = 0
                try:
                    count_req = urllib.request.Request(
                        PLEX_BASE_URL + f"/library/sections/{key}/all"
                        "?X-Plex-Container-Size=0",
                        headers=headers,
                    )
                    with urllib.request.urlopen(count_req, timeout=5) as cr:
                        count_data = json.loads(cr.read().decode())
                        count = count_data.get("MediaContainer", {}).get("size", 0)
                except Exception:
                    pass
                libraries.append({
                    "key": key,
                    "title": d.get("title"),
                    "type": d.get("type"),
                    "count": count,
                })
    except Exception:
        libraries = []

    recently_added = []
    try:
        req = urllib.request.Request(
            PLEX_BASE_URL + "/library/recentlyAdded"
            "?X-Plex-Container-Start=0&X-Plex-Container-Size=10",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            for item in data.get("MediaContainer", {}).get("Metadata", []):
                recently_added.append({
                    "title": item.get("title"),
                    "type": item.get("type"),
                    "added_at": item.get("addedAt"),
                    "year": item.get("year"),
                    "library": item.get("librarySectionTitle"),
                    "thumb": item.get("thumb"),
                })
    except Exception:
        recently_added = []

    return {"libraries": libraries, "recently_added": recently_added}
