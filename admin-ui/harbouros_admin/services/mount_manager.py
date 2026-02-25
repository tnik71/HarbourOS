"""NAS mount manager — CRUD operations + systemd unit generation."""

import json
import os
import re
import subprocess
import uuid


def _sudo(cmd):
    """Prepend sudo to a command when running as non-root."""
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        return ["sudo"] + cmd
    return cmd

CONFIG_DIR = "/etc/harbouros"
CONFIG_FILE = os.path.join(CONFIG_DIR, "mounts.json")
MOUNT_BASE = "/media/nas"
SYSTEMD_DIR = "/etc/systemd/system"

# Dev mode uses temp paths
if os.environ.get("HARBOUROS_DEV"):
    import tempfile
    _dev_dir = tempfile.mkdtemp(prefix="harbouros-dev-")
    CONFIG_DIR = _dev_dir
    CONFIG_FILE = os.path.join(_dev_dir, "mounts.json")
    MOUNT_BASE = os.path.join(_dev_dir, "media", "nas")
    SYSTEMD_DIR = os.path.join(_dev_dir, "systemd")
    os.makedirs(MOUNT_BASE, exist_ok=True)
    os.makedirs(SYSTEMD_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"mounts": []}, f)


def _load_config():
    """Load mount configuration from JSON file."""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"mounts": []}


def _save_config(config):
    """Save mount configuration to JSON file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _sanitize_name(name):
    """Sanitize mount name for use in paths and unit names."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())


def _mount_path(name):
    """Get the mount point path for a named mount."""
    return os.path.join(MOUNT_BASE, _sanitize_name(name))


def _validate_host(host):
    """Validate host is a reasonable hostname or IP, not localhost."""
    if not host or not isinstance(host, str):
        raise ValueError("Host is required")
    host = host.strip()
    if not re.match(r'^[a-zA-Z0-9._-]+$', host):
        raise ValueError("Host contains invalid characters")
    if host in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
        raise ValueError("Cannot mount localhost")
    if len(host) > 253:
        raise ValueError("Hostname too long")
    return host


def _validate_share(share):
    """Validate share path — block path traversal."""
    if not share or not isinstance(share, str):
        raise ValueError("Share path is required")
    if '..' in share:
        raise ValueError("Share path cannot contain '..'")
    return share


_SAFE_MOUNT_OPTIONS = {
    'nfsvers', 'vers', 'soft', 'hard', 'timeo', 'retrans', 'ro', 'rw',
    'credentials', 'iocharset', 'file_mode', 'dir_mode', 'uid', 'gid',
    'sec', 'noacl', 'nolock', 'intr',
}


def _validate_options(options):
    """Validate mount options against a whitelist."""
    if not options:
        return None
    for opt in options.split(','):
        key = opt.split('=')[0].strip()
        if key and key not in _SAFE_MOUNT_OPTIONS:
            raise ValueError(f"Mount option '{key}' is not allowed")
    return options


def _systemd_escape(path):
    """Convert a path to a systemd unit name using systemd-escape."""
    try:
        result = subprocess.run(
            _sudo(["systemd-escape", "--path", path]),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    # Fallback: escape each path component's hyphens, then join with -
    parts = path.strip("/").split("/")
    escaped = []
    for part in parts:
        escaped.append(part.replace("\\", "\\x5c").replace("-", "\\x2d"))
    return "-".join(escaped)


def _generate_mount_unit(mount):
    """Generate a systemd .mount unit file content."""
    mount_path = _mount_path(mount["name"])
    unit_name = _systemd_escape(mount_path)

    if mount["type"] == "nfs":
        share = mount['share'] if mount['share'].startswith('/') else f"/{mount['share']}"
        source = f"{mount['host']}:{share}"
        fs_type = "nfs"
        options = mount.get("options", "nfsvers=4,soft,timeo=150,retrans=3")
    else:  # smb
        share = mount['share'].lstrip('/')
        source = f"//{mount['host']}/{share}"
        fs_type = "cifs"
        creds_file = os.path.join(CONFIG_DIR, f"smb-{_sanitize_name(mount['name'])}.creds")
        options = mount.get(
            "options",
            f"vers=3.0,credentials={creds_file},iocharset=utf8,file_mode=0775,dir_mode=0775"
        )

    return f"""[Unit]
Description=NAS Mount: {mount['name']}
After=network-online.target
Wants=network-online.target

[Mount]
What={source}
Where={mount_path}
Type={fs_type}
Options={options}
TimeoutSec=30

[Install]
WantedBy=multi-user.target
""", unit_name


def _generate_automount_unit(mount):
    """Generate a systemd .automount unit file content."""
    mount_path = _mount_path(mount["name"])
    unit_name = _systemd_escape(mount_path)

    return f"""[Unit]
Description=Automount NAS: {mount['name']}
After=network-online.target
Wants=network-online.target

[Automount]
Where={mount_path}
TimeoutIdleSec=600

[Install]
WantedBy=multi-user.target
""", unit_name


def _write_smb_credentials(mount):
    """Write SMB credentials file with restricted permissions."""
    if mount["type"] != "smb":
        return
    creds_file = os.path.join(CONFIG_DIR, f"smb-{_sanitize_name(mount['name'])}.creds")
    content = (
        f"username={mount.get('username', '')}\n"
        f"password={mount.get('password', '')}\n"
        f"domain={mount.get('domain', 'WORKGROUP')}\n"
    )
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(
            ["sudo", "tee", creds_file],
            input=content, capture_output=True, text=True, timeout=5
        )
        subprocess.run(["sudo", "chmod", "600", creds_file], timeout=5)
    else:
        fd = os.open(creds_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(content)


def _write_privileged_file(path, content):
    """Write to a root-owned path, using sudo tee if non-root."""
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(
            ["sudo", "tee", path],
            input=content, capture_output=True, text=True, timeout=5
        )
    else:
        with open(path, "w") as f:
            f.write(content)


def _install_units(mount):
    """Write systemd mount and automount units to disk and enable them."""
    mount_content, unit_name = _generate_mount_unit(mount)
    automount_content, _ = _generate_automount_unit(mount)

    mount_unit_path = os.path.join(SYSTEMD_DIR, f"{unit_name}.mount")
    automount_unit_path = os.path.join(SYSTEMD_DIR, f"{unit_name}.automount")

    _write_privileged_file(mount_unit_path, mount_content)
    _write_privileged_file(automount_unit_path, automount_content)

    if not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(_sudo(["systemctl", "daemon-reload"]), check=False, timeout=10)
        subprocess.run(
            _sudo(["systemctl", "enable", f"{unit_name}.automount"]),
            check=False, timeout=10
        )


def _remove_privileged_file(path):
    """Remove a root-owned file, using sudo if non-root."""
    if not os.path.exists(path):
        return
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(["sudo", "rm", path], check=False, timeout=5)
    else:
        os.remove(path)


def _remove_units(mount):
    """Remove systemd mount and automount units."""
    mount_path = _mount_path(mount["name"])
    unit_name = _systemd_escape(mount_path)

    if not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(
            _sudo(["systemctl", "disable", "--now", f"{unit_name}.automount"]),
            check=False, timeout=10
        )
        subprocess.run(
            _sudo(["systemctl", "disable", "--now", f"{unit_name}.mount"]),
            check=False, timeout=10
        )

    for ext in (".mount", ".automount"):
        _remove_privileged_file(os.path.join(SYSTEMD_DIR, f"{unit_name}{ext}"))

    if not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(_sudo(["systemctl", "daemon-reload"]), check=False, timeout=10)

    # Remove SMB credentials if applicable
    creds_file = os.path.join(CONFIG_DIR, f"smb-{_sanitize_name(mount['name'])}.creds")
    _remove_privileged_file(creds_file)


def list_mounts():
    """List all configured mounts with their current status."""
    config = _load_config()
    mounts = []
    for m in config.get("mounts", []):
        mount_path = _mount_path(m["name"])
        mounted = os.path.ismount(mount_path) if not os.environ.get("HARBOUROS_DEV") else False
        mounts.append({
            "id": m["id"],
            "name": m["name"],
            "type": m["type"],
            "host": m["host"],
            "share": m["share"],
            "target": mount_path,
            "status": "mounted" if mounted else "unmounted",
        })
    return mounts


def add_mount(name, mount_type, host, share, **kwargs):
    """Add a new NAS mount."""
    host = _validate_host(host)
    share = _validate_share(share)
    if kwargs.get("options"):
        kwargs["options"] = _validate_options(kwargs["options"])
    config = _load_config()
    mount = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "type": mount_type,
        "host": host,
        "share": share,
        **{k: v for k, v in kwargs.items() if v is not None},
    }
    config["mounts"].append(mount)
    _save_config(config)

    # Create mount point directory
    mount_path = _mount_path(name)
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        subprocess.run(_sudo(["mkdir", "-p", mount_path]), check=False, timeout=5)
    else:
        os.makedirs(mount_path, exist_ok=True)

    # Write SMB credentials if needed
    _write_smb_credentials(mount)

    # Install systemd units
    _install_units(mount)

    return mount


def update_mount(mount_id, **kwargs):
    """Update an existing mount configuration."""
    config = _load_config()
    for i, m in enumerate(config["mounts"]):
        if m["id"] == mount_id:
            _remove_units(m)
            config["mounts"][i].update(
                {k: v for k, v in kwargs.items() if v is not None}
            )
            _save_config(config)
            _write_smb_credentials(config["mounts"][i])
            _install_units(config["mounts"][i])
            return config["mounts"][i]
    return None


def remove_mount(mount_id):
    """Remove a mount and its systemd units."""
    config = _load_config()
    for i, m in enumerate(config["mounts"]):
        if m["id"] == mount_id:
            _remove_units(m)
            mount_path = _mount_path(m["name"])
            if os.path.isdir(mount_path):
                try:
                    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
                        subprocess.run(_sudo(["rmdir", mount_path]), check=False, timeout=5)
                    else:
                        os.rmdir(mount_path)
                except OSError:
                    pass  # Directory not empty or still mounted
            config["mounts"].pop(i)
            _save_config(config)
            return True
    return False


def mount_share(mount_id):
    """Mount a specific share now."""
    config = _load_config()
    for m in config["mounts"]:
        if m["id"] == mount_id:
            mount_path = _mount_path(m["name"])
            unit_name = _systemd_escape(mount_path)
            if os.environ.get("HARBOUROS_DEV"):
                return True, "OK (dev mode)"
            result = subprocess.run(
                _sudo(["systemctl", "start", f"{unit_name}.mount"]),
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, "Mounted successfully"
            return False, result.stderr.strip()
    return False, "Mount not found"


def unmount_share(mount_id):
    """Unmount a specific share."""
    config = _load_config()
    for m in config["mounts"]:
        if m["id"] == mount_id:
            mount_path = _mount_path(m["name"])
            unit_name = _systemd_escape(mount_path)
            if os.environ.get("HARBOUROS_DEV"):
                return True, "OK (dev mode)"
            result = subprocess.run(
                _sudo(["systemctl", "stop", f"{unit_name}.mount"]),
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return True, "Unmounted successfully"
            return False, result.stderr.strip()
    return False, "Mount not found"


def test_connection(host, mount_type, share=None):
    """Test NAS connectivity."""
    if os.environ.get("HARBOUROS_DEV"):
        return True, f"Connection to {host} successful (dev mode)"

    if mount_type == "nfs":
        result = subprocess.run(
            _sudo(["showmount", "-e", host]),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, f"Cannot reach NFS server: {result.stderr.strip()}"
    else:  # smb
        result = subprocess.run(
            _sudo(["smbclient", "-L", f"//{host}", "-N"]),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, f"Cannot reach SMB server: {result.stderr.strip()}"


def discover_devices():
    """Discover NAS devices on the local network via mDNS."""
    if os.environ.get("HARBOUROS_DEV"):
        return [
            {
                "name": "ReadyNAS 316",
                "hostname": "readynas.local",
                "address": "192.168.1.50",
                "services": ["nfs", "smb"],
            },
            {
                "name": "Synology DS920+",
                "hostname": "synology.local",
                "address": "192.168.1.60",
                "services": ["smb", "nfs"],
            },
            {
                "name": "TrueNAS Core",
                "hostname": "truenas.local",
                "address": "192.168.1.70",
                "services": ["nfs"],
            },
        ]

    devices = {}  # keyed by IP for dedup

    for svc_type, proto in [("_smb._tcp", "smb"), ("_nfs._tcp", "nfs")]:
        try:
            result = subprocess.run(
                _sudo(["avahi-browse", "-tprk", svc_type]),
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.startswith("="):
                        continue
                    parts = line.split(";")
                    if len(parts) < 9:
                        continue
                    name = parts[3]
                    hostname = parts[6]
                    address = parts[7]
                    if address in devices:
                        if proto not in devices[address]["services"]:
                            devices[address]["services"].append(proto)
                    else:
                        devices[address] = {
                            "name": name,
                            "hostname": hostname,
                            "address": address,
                            "services": [proto],
                        }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return list(devices.values())


def discover_shares(host, share_type, username=None, password=None):
    """List available shares from a NAS host."""
    if os.environ.get("HARBOUROS_DEV"):
        if share_type == "nfs":
            return [
                {"name": "/volume1/media", "comment": "*"},
                {"name": "/volume1/music", "comment": "192.168.1.0/24"},
                {"name": "/volume1/photos", "comment": "*"},
            ]
        else:
            return [
                {"name": "media", "comment": "Media files"},
                {"name": "music", "comment": "Music collection"},
                {"name": "photos", "comment": "Photo library"},
            ]

    if share_type == "nfs":
        return _discover_nfs_shares(host)
    else:
        return _discover_smb_shares(host, username, password)


def _discover_nfs_shares(host):
    """Parse NFS exports from showmount output."""
    try:
        result = subprocess.run(
            _sudo(["showmount", "-e", host]),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []
        shares = []
        for line in result.stdout.strip().split("\n")[1:]:  # skip header
            parts = line.strip().split()
            if len(parts) >= 1:
                shares.append({
                    "name": parts[0],
                    "comment": " ".join(parts[1:]) if len(parts) > 1 else "",
                })
        return shares
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _discover_smb_shares(host, username=None, password=None):
    """Parse SMB shares from smbclient output."""
    try:
        if username and password:
            cmd = _sudo(["smbclient", "-L", f"//{host}", "-U", f"{username}%{password}"])
        else:
            cmd = _sudo(["smbclient", "-L", f"//{host}", "-N"])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        shares = []
        for line in result.stdout.split("\n"):
            match = re.match(r"^\s+(\S+)\s+Disk\s+(.*)", line)
            if match:
                name = match.group(1)
                comment = match.group(2).strip()
                if name.endswith("$"):
                    continue
                shares.append({"name": name, "comment": comment})
        return shares
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
