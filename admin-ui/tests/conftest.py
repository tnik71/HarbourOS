"""Test fixtures for HarbourOS Admin UI."""

import os
import tempfile

import pytest

# Enable dev mode for all tests
os.environ["HARBOUROS_DEV"] = "1"

from harbouros_admin.app import create_app  # noqa: E402
from harbouros_admin.services import auth_service  # noqa: E402


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Authenticated test client — session is pre-authed for backward compatibility."""
    c = app.test_client()
    # Set session as authenticated so login_required doesn't block tests
    with c.session_transaction() as sess:
        sess["authenticated"] = True
    return c


@pytest.fixture
def anon_client(app):
    """Unauthenticated test client for testing login flows."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_setup_flag():
    """Ensure the setup flag exists and auth config is reset for tests."""
    flag = os.path.join(tempfile.gettempdir(), "harbouros-setup-complete")
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    with open(flag, "w") as f:
        f.write("1")
    # Reset auth config to default password before each test
    if os.path.exists(auth_service.AUTH_CONFIG):
        os.remove(auth_service.AUTH_CONFIG)
    yield
    # Clean up
    if os.path.exists(flag):
        os.remove(flag)
