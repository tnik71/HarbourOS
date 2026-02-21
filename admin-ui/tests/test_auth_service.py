"""Tests for auth_service module."""

import hashlib
import os

import pytest

# Enable dev mode for all tests
os.environ["HARBOUROS_DEV"] = "1"

from harbouros_admin.services import auth_service  # noqa: E402


@pytest.fixture(autouse=True)
def reset_auth_config():
    """Reset the auth config to defaults before each test."""
    config = {
        "password_hash": auth_service._hash_password("harbouros"),
        "password_changed": False,
    }
    # Preserve secret key if it exists
    try:
        existing = auth_service._load_auth_config()
        if "secret_key" in existing:
            config["secret_key"] = existing["secret_key"]
    except Exception:
        pass
    auth_service._save_auth_config(config)
    yield


def test_verify_default_password():
    """Default password 'harbouros' is accepted."""
    assert auth_service.verify_password("harbouros") is True


def test_verify_wrong_password():
    """Wrong password is rejected."""
    assert auth_service.verify_password("wrong") is False


def test_change_password():
    """Changing password updates stored hash."""
    success, msg = auth_service.change_password("harbouros", "newpass")
    assert success is True
    assert auth_service.verify_password("newpass") is True


def test_change_password_wrong_current():
    """Cannot change password with wrong current."""
    success, msg = auth_service.change_password("wrong", "newpass")
    assert success is False


def test_is_password_changed():
    """Password changed flag is tracked."""
    assert auth_service.is_password_changed() is False
    auth_service.change_password("harbouros", "temp1234")
    assert auth_service.is_password_changed() is True


def test_secret_key_generation():
    """Secret key is generated and persisted."""
    key = auth_service.get_or_create_secret_key()
    assert key is not None
    assert len(key) == 64  # 32 bytes hex = 64 chars
    # Calling again returns same key
    assert auth_service.get_or_create_secret_key() == key


def test_hash_is_bcrypt():
    """Password hashes use bcrypt format."""
    h = auth_service._hash_password("test")
    assert h.startswith("$2b$")


def test_legacy_sha256_migration():
    """Legacy SHA-256 hash is auto-upgraded to bcrypt on login."""
    legacy_hash = hashlib.sha256("harbouros".encode()).hexdigest()
    config = auth_service._load_auth_config()
    config["password_hash"] = legacy_hash
    auth_service._save_auth_config(config)

    # Verify still works with legacy hash
    assert auth_service.verify_password("harbouros") is True

    # Hash should now be upgraded to bcrypt
    config = auth_service._load_auth_config()
    assert config["password_hash"].startswith("$2b$")

    # Still verifies after upgrade
    assert auth_service.verify_password("harbouros") is True


def test_legacy_sha256_wrong_password():
    """Legacy SHA-256 hash rejects wrong password without upgrading."""
    legacy_hash = hashlib.sha256("harbouros".encode()).hexdigest()
    config = auth_service._load_auth_config()
    config["password_hash"] = legacy_hash
    auth_service._save_auth_config(config)

    assert auth_service.verify_password("wrong") is False

    # Hash should still be legacy (not upgraded)
    config = auth_service._load_auth_config()
    assert config["password_hash"] == legacy_hash
