"""HarbourOS config backup and restore service."""

import glob
import io
import logging
import os
import subprocess
import tarfile
from datetime import datetime

from .plex_service import PLEX_PREFS_PATH

log = logging.getLogger(__name__)

# Files and glob patterns to include in the backup (order does not matter)
_BACKUP_PATHS = [
    "/etc/harbouros/admin.json",
    "/etc/harbouros/mounts.json",
    "/etc/harbouros/.setup-complete",
    "/etc/dhcpcd.conf",
    PLEX_PREFS_PATH,
]

# Glob patterns (expanded at backup time)
_BACKUP_GLOBS = [
    "/etc/harbouros/smb-*.creds",
    "/etc/harbouros/.migration-*",
]


def create_backup():
    """Create an in-memory .tar.gz of all HarbourOS config files.

    Returns:
        (bytes, filename) — the raw gzip-compressed tar bytes and a
        suggested download filename like ``harbouros-backup-2026-03-14.tar.gz``.
    """
    if os.environ.get("HARBOUROS_DEV"):
        # Return a minimal valid tar.gz in dev mode
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            content = b'{"password_hash": "dev", "password_changed": true, "secret_key": "dev"}'
            info = tarfile.TarInfo(name="etc/harbouros/admin.json")
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
        filename = "harbouros-backup-dev.tar.gz"
        return buf.getvalue(), filename

    buf = io.BytesIO()
    added = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        candidates = list(_BACKUP_PATHS)
        for pattern in _BACKUP_GLOBS:
            candidates.extend(glob.glob(pattern))

        for path in candidates:
            if not os.path.isfile(path):
                log.debug("Backup: skipping missing file %s", path)
                continue
            # Store with a relative arcname (strip leading /) so the tar is portable
            arcname = path.lstrip("/")
            try:
                tf.add(path, arcname=arcname)
                added += 1
                log.debug("Backup: added %s", path)
            except OSError as e:
                log.warning("Backup: could not read %s: %s", path, e)

    log.info("Backup created: %d files", added)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"harbouros-backup-{date_str}.tar.gz"
    return buf.getvalue(), filename


def restore_backup(fileobj):
    """Restore config from an uploaded .tar.gz backup.

    Extracts files back to their absolute paths (prepending / to arcnames).
    Restarts the harbouros service afterwards so new config takes effect.

    Args:
        fileobj: a file-like object containing the .tar.gz data.

    Returns:
        (success: bool, message: str)
    """
    if os.environ.get("HARBOUROS_DEV"):
        return True, "Backup restored successfully (dev mode)"

    try:
        with tarfile.open(fileobj=fileobj, mode="r:gz") as tf:
            members = tf.getmembers()
            names = [m.name for m in members]

            # Sanity check — must look like a HarbourOS backup
            if not any("etc/harbouros/admin.json" in n for n in names):
                return False, "This does not appear to be a valid HarbourOS backup (missing admin.json)"

            # Restore each member to its absolute path
            for member in members:
                # Only extract regular files and directories — never symlinks or devices
                if not (member.isfile() or member.isdir()):
                    log.warning("Restore: skipping non-regular member %s", member.name)
                    continue

                # Restore absolute path by prepending /
                abs_path = "/" + member.name.lstrip("/")

                # Safety: only allow paths we expect
                allowed_prefixes = (
                    "/etc/harbouros/",
                    "/etc/dhcpcd.conf",
                    "/var/lib/plexmediaserver/",
                )
                if not any(abs_path.startswith(p) for p in allowed_prefixes):
                    log.warning("Restore: skipping unexpected path %s", abs_path)
                    continue

                if member.isdir():
                    os.makedirs(abs_path, exist_ok=True)
                    continue

                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with tf.extractfile(member) as src, open(abs_path, "wb") as dst:
                    dst.write(src.read())

                # Preserve permissions for sensitive files
                if abs_path.endswith(".creds"):
                    os.chmod(abs_path, 0o600)

                log.info("Restore: wrote %s", abs_path)

    except tarfile.TarError as e:
        return False, f"Failed to read backup file: {e}"
    except OSError as e:
        return False, f"Failed to restore files: {e}"

    # Restart the service so it picks up the restored config
    try:
        cmd = ["systemctl", "restart", "harbouros"]
        if os.getuid() != 0:
            cmd = ["sudo"] + cmd
        subprocess.run(cmd, check=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        log.warning("Restore: service restart failed: %s", e)
        # Don't fail the restore just because the restart failed
        return True, "Backup restored. Service restart failed — please restart manually."

    return True, "Backup restored successfully. Service is restarting..."
