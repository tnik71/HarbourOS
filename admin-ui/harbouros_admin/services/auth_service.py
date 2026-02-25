"""Authentication and password management service."""

import hashlib
import json
import os
import secrets
import subprocess

import bcrypt

CONFIG_DIR = "/etc/harbouros"
AUTH_CONFIG = os.path.join(CONFIG_DIR, "admin.json")

if os.environ.get("HARBOUROS_DEV"):
    import tempfile
    _dev_dir = os.path.join(tempfile.gettempdir(), "harbouros-dev")
    os.makedirs(_dev_dir, exist_ok=True)
    CONFIG_DIR = _dev_dir
    AUTH_CONFIG = os.path.join(_dev_dir, "admin.json")

_DEFAULT_HASH = bcrypt.hashpw("harbouros".encode(), bcrypt.gensalt()).decode()


def _load_auth_config():
    """Load auth config, creating defaults if missing."""
    try:
        with open(AUTH_CONFIG) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {
            "password_hash": _DEFAULT_HASH,
            "password_changed": False,
        }
        _save_auth_config(config)
        return config


def _save_auth_config(config):
    """Save auth config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(AUTH_CONFIG, "w") as f:
        json.dump(config, f, indent=2)


def _hash_password(password):
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _is_legacy_hash(stored_hash):
    """Check if a stored hash is old-style SHA-256 (64-char hex)."""
    return len(stored_hash) == 64 and all(c in "0123456789abcdef" for c in stored_hash)


def verify_password(password):
    """Check if password matches stored hash. Auto-upgrades legacy SHA-256 hashes."""
    config = _load_auth_config()
    stored = config["password_hash"]

    if _is_legacy_hash(stored):
        # Legacy SHA-256 check
        if hashlib.sha256(password.encode()).hexdigest() == stored:
            # Upgrade to bcrypt on successful login
            config["password_hash"] = _hash_password(password)
            _save_auth_config(config)
            return True
        return False

    return bcrypt.checkpw(password.encode(), stored.encode())


def change_password(current_password, new_password):
    """Change the admin password."""
    if not verify_password(current_password):
        return False, "Current password is incorrect"
    if len(new_password) < 8:
        return False, "New password must be at least 8 characters"

    config = _load_auth_config()
    config["password_hash"] = _hash_password(new_password)
    config["password_changed"] = True
    _save_auth_config(config)

    if not os.environ.get("HARBOUROS_DEV"):
        # Try to sync system password (best-effort, non-blocking)
        # Detect the main non-root user
        try:
            result = subprocess.run(
                ["bash", "-c", "getent passwd harbouros >/dev/null 2>&1 && echo harbouros || "
                 "awk -F: '$3 >= 1000 && $3 < 65534 {print $1; exit}' /etc/passwd"],
                capture_output=True, text=True, timeout=5
            )
            sys_user = result.stdout.strip()
            if sys_user:
                chpasswd_cmd = ["chpasswd"]
                if os.getuid() != 0:
                    chpasswd_cmd = ["sudo", "chpasswd"]
                subprocess.run(
                    chpasswd_cmd,
                    input=f"{sys_user}:{new_password}",
                    capture_output=True, text=True, timeout=10
                )
        except Exception:
            pass  # System password sync is best-effort

    return True, "Password changed successfully"


def is_password_changed():
    """Check if the default password has been changed."""
    config = _load_auth_config()
    return config.get("password_changed", False)


def get_or_create_secret_key():
    """Get or generate the Flask secret key for sessions."""
    config = _load_auth_config()
    if "secret_key" not in config:
        config["secret_key"] = secrets.token_hex(32)
        _save_auth_config(config)
    return config["secret_key"]
