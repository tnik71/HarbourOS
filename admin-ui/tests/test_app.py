"""Tests for HarbourOS Admin UI routes and API endpoints."""

import json
import os


def test_dashboard_page(client):
    """Dashboard page loads successfully."""
    resp = client.get("/")
    assert resp.status_code == 200


def test_nas_page(client):
    """NAS page loads successfully."""
    resp = client.get("/nas")
    assert resp.status_code == 200
    assert b"NAS Storage" in resp.data


def test_plex_page(client):
    """Plex page loads successfully."""
    resp = client.get("/plex")
    assert resp.status_code == 200
    assert b"Plex Media Server" in resp.data


def test_network_page(client):
    """Network page loads successfully."""
    resp = client.get("/network")
    assert resp.status_code == 200
    assert b"Network" in resp.data


def test_setup_page(client):
    """Setup page loads successfully."""
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert b"Welcome to" in resp.data


# --- API: System ---

def test_api_system_status(client):
    """System status API returns expected fields."""
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cpu_percent" in data
    assert "memory" in data
    assert "disk" in data
    assert "uptime" in data
    assert "percent" in data["memory"]
    assert "total_mb" in data["memory"]


# --- API: Plex ---

def test_api_plex_status(client):
    """Plex status API returns status info."""
    resp = client.get("/api/plex/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "running" in data
    assert "version" in data


def test_api_plex_action_start(client):
    """Plex start action succeeds in dev mode."""
    resp = client.post(
        "/api/plex/action",
        data=json.dumps({"action": "start"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_plex_action_missing(client):
    """Plex action with missing field returns 400."""
    resp = client.post(
        "/api/plex/action",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_plex_action_invalid(client):
    """Plex action with invalid action returns error."""
    resp = client.post(
        "/api/plex/action",
        data=json.dumps({"action": "explode"}),
        content_type="application/json",
    )
    data = resp.get_json()
    assert data["success"] is False


def test_api_plex_logs(client):
    """Plex logs API returns log lines."""
    resp = client.get("/api/plex/logs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_api_plex_libraries(client):
    """Plex libraries API returns library and recently added data."""
    resp = client.get("/api/plex/libraries")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "libraries" in data
    assert "recently_added" in data
    assert isinstance(data["libraries"], list)
    assert isinstance(data["recently_added"], list)


def test_api_plex_libraries_has_items(client):
    """Plex libraries API returns mock libraries in dev mode."""
    resp = client.get("/api/plex/libraries")
    data = resp.get_json()
    assert len(data["libraries"]) >= 1
    lib = data["libraries"][0]
    assert "title" in lib
    assert "type" in lib
    assert "count" in lib


def test_api_plex_libraries_recently_added(client):
    """Plex libraries API returns recently added items in dev mode."""
    resp = client.get("/api/plex/libraries")
    data = resp.get_json()
    assert len(data["recently_added"]) >= 1
    item = data["recently_added"][0]
    assert "title" in item
    assert "type" in item
    assert "added_at" in item


def test_api_plex_libraries_auth_required(anon_client):
    """Plex libraries API requires authentication."""
    resp = anon_client.get("/api/plex/libraries")
    assert resp.status_code == 401


# --- API: Mounts ---

def test_api_mounts_list_empty(client):
    """Mount list starts empty."""
    resp = client.get("/api/mounts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "mounts" in data


def test_api_mounts_add_nfs(client):
    """Adding an NFS mount succeeds."""
    resp = client.post(
        "/api/mounts",
        data=json.dumps({
            "name": "TestMovies",
            "type": "nfs",
            "host": "192.168.1.100",
            "share": "/media/Movies",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["mount"]["name"] == "TestMovies"
    assert data["mount"]["type"] == "nfs"
    assert "id" in data["mount"]


def test_api_mounts_add_missing_fields(client):
    """Adding a mount with missing fields returns 400."""
    resp = client.post(
        "/api/mounts",
        data=json.dumps({"name": "Test"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_mounts_add_invalid_type(client):
    """Adding a mount with invalid type returns 400."""
    resp = client.post(
        "/api/mounts",
        data=json.dumps({
            "name": "Test",
            "type": "ftp",
            "host": "192.168.1.1",
            "share": "/test",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_mounts_test_connection(client):
    """Test connection API works in dev mode."""
    resp = client.post(
        "/api/mounts/test",
        data=json.dumps({"host": "192.168.1.100", "type": "nfs"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_mounts_test_missing_host(client):
    """Test connection with missing host returns 400."""
    resp = client.post(
        "/api/mounts/test",
        data=json.dumps({"type": "nfs"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_mounts_delete_nonexistent(client):
    """Deleting a nonexistent mount returns 404."""
    resp = client.delete("/api/mounts/nonexistent")
    assert resp.status_code == 404


def test_api_mounts_update(client):
    """Updating an existing mount succeeds."""
    # Create a mount first
    resp = client.post(
        "/api/mounts",
        data=json.dumps({
            "name": "UpdateMe",
            "type": "nfs",
            "host": "192.168.1.100",
            "share": "/media/Movies",
        }),
        content_type="application/json",
    )
    mount_id = resp.get_json()["mount"]["id"]
    # Update it
    resp = client.put(
        f"/api/mounts/{mount_id}",
        data=json.dumps({"name": "Updated"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["mount"]["name"] == "Updated"


def test_api_mounts_update_nonexistent(client):
    """Updating a nonexistent mount returns 404."""
    resp = client.put(
        "/api/mounts/nonexistent",
        data=json.dumps({"name": "Nope"}),
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_api_mounts_mount_share(client):
    """Mounting a share succeeds in dev mode."""
    resp = client.post(
        "/api/mounts",
        data=json.dumps({
            "name": "MountMe",
            "type": "nfs",
            "host": "192.168.1.100",
            "share": "/media/Movies",
        }),
        content_type="application/json",
    )
    mount_id = resp.get_json()["mount"]["id"]
    resp = client.post(f"/api/mounts/{mount_id}/mount")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_mounts_unmount_share(client):
    """Unmounting a share succeeds in dev mode."""
    resp = client.post(
        "/api/mounts",
        data=json.dumps({
            "name": "UnmountMe",
            "type": "nfs",
            "host": "192.168.1.100",
            "share": "/media/Movies",
        }),
        content_type="application/json",
    )
    mount_id = resp.get_json()["mount"]["id"]
    resp = client.post(f"/api/mounts/{mount_id}/unmount")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# --- API: Discovery ---

def test_api_discover_devices(client):
    """Device discovery API returns device list."""
    resp = client.get("/api/mounts/discover")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "devices" in data
    assert isinstance(data["devices"], list)
    assert len(data["devices"]) >= 1
    device = data["devices"][0]
    assert "name" in device
    assert "address" in device
    assert "services" in device


def test_api_discover_shares_nfs(client):
    """Share discovery API returns NFS shares."""
    resp = client.post(
        "/api/mounts/discover/shares",
        data=json.dumps({"host": "192.168.1.50", "type": "nfs"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "shares" in data
    assert len(data["shares"]) >= 1


def test_api_discover_shares_smb(client):
    """Share discovery API returns SMB shares."""
    resp = client.post(
        "/api/mounts/discover/shares",
        data=json.dumps({"host": "192.168.1.50", "type": "smb"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "shares" in data
    assert len(data["shares"]) >= 1


def test_api_discover_shares_missing_host(client):
    """Share discovery with missing host returns 400."""
    resp = client.post(
        "/api/mounts/discover/shares",
        data=json.dumps({"type": "nfs"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_discover_shares_invalid_type(client):
    """Share discovery with invalid type returns 400."""
    resp = client.post(
        "/api/mounts/discover/shares",
        data=json.dumps({"host": "192.168.1.50", "type": "ftp"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# --- API: Network ---

def test_api_network_info(client):
    """Network info API returns expected fields."""
    resp = client.get("/api/network")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "hostname" in data
    assert "ip_address" in data


def test_api_network_set_hostname(client):
    """Setting hostname works in dev mode."""
    resp = client.post(
        "/api/network",
        data=json.dumps({"hostname": "test-harbouros"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_network_no_changes(client):
    """Posting empty network update returns 400."""
    resp = client.post(
        "/api/network",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# --- API: Auth ---

def test_login_page(anon_client):
    """Login page loads for unauthenticated users."""
    resp = anon_client.get("/login")
    assert resp.status_code == 200
    assert b"Login" in resp.data or b"login" in resp.data


def test_login_success(anon_client):
    """Login with correct password succeeds."""
    resp = anon_client.post(
        "/login",
        data=json.dumps({"password": "harbouros"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_login_failure(anon_client):
    """Login with wrong password fails."""
    resp = anon_client.post(
        "/login",
        data=json.dumps({"password": "wrong"}),
        content_type="application/json",
    )
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["success"] is False


def test_login_rate_limiting(anon_client):
    """Login is rate-limited after too many failed attempts."""
    from harbouros_admin.app import _login_attempts
    _login_attempts.clear()
    for _ in range(5):
        anon_client.post(
            "/login",
            data=json.dumps({"password": "wrong"}),
            content_type="application/json",
        )
    resp = anon_client.post(
        "/login",
        data=json.dumps({"password": "wrong"}),
        content_type="application/json",
    )
    assert resp.status_code == 429
    data = resp.get_json()
    assert "Too many" in data["error"]
    _login_attempts.clear()


def test_auth_required_redirect(anon_client):
    """Unauthenticated page request redirects to login."""
    resp = anon_client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_auth_required_api(anon_client):
    """Unauthenticated API request returns 401."""
    resp = anon_client.get("/api/system/status")
    assert resp.status_code == 401


def test_logout(client):
    """Logout clears session."""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_auth_status(client):
    """Auth status API returns auth state."""
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "authenticated" in data
    assert "password_changed" in data


# --- API: System Power ---

def test_api_power_reboot(client):
    """Reboot action succeeds in dev mode."""
    resp = client.post(
        "/api/system/power",
        data=json.dumps({"action": "reboot"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_power_shutdown(client):
    """Shutdown action succeeds in dev mode."""
    resp = client.post(
        "/api/system/power",
        data=json.dumps({"action": "shutdown"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_power_invalid(client):
    """Invalid power action returns 400."""
    resp = client.post(
        "/api/system/power",
        data=json.dumps({"action": "explode"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# --- API: System Logs ---

def test_api_system_logs(client):
    """System logs API returns log lines."""
    resp = client.get("/api/system/logs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_api_system_logs_filtered(client):
    """System logs API works with service filter."""
    resp = client.get("/api/system/logs?service=plexmediaserver&lines=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "logs" in data


# --- API: System Services ---

def test_api_system_services(client):
    """Services API returns service status list."""
    resp = client.get("/api/system/services")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "services" in data
    assert isinstance(data["services"], list)
    assert len(data["services"]) >= 1
    svc = data["services"][0]
    assert "name" in svc
    assert "active" in svc


# --- API: System Updates ---

def test_api_update_status(client):
    """Update status API returns available count."""
    resp = client.get("/api/system/update/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "available" in data
    assert "packages" in data


def test_api_run_update(client):
    """Run update API returns output."""
    resp = client.post("/api/system/update")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "success" in data
    assert "output" in data


# --- API: System Disk ---

def test_api_disk_details(client):
    """Disk details API returns partition info."""
    resp = client.get("/api/system/disk")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "partitions" in data
    assert isinstance(data["partitions"], list)


# --- API: System Password ---

def test_api_change_password_success(client):
    """Changing password with correct current password succeeds."""
    resp = client.post(
        "/api/system/password",
        data=json.dumps({"current": "harbouros", "new": "newpass123"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_change_password_wrong_current(client):
    """Changing password with wrong current password fails."""
    resp = client.post(
        "/api/system/password",
        data=json.dumps({"current": "wrong", "new": "newpass123"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_api_change_password_missing_fields(client):
    """Changing password with missing fields returns 400."""
    resp = client.post(
        "/api/system/password",
        data=json.dumps({"current": "harbouros"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# --- API: Plex Update Log ---

def test_api_plex_update_log(client):
    """Plex update log API returns log lines."""
    resp = client.get("/api/plex/update-log")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_api_plex_check_update(client):
    """Plex check update API works in dev mode."""
    resp = client.post("/api/plex/check-update")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# --- API: Network Static IP ---

def test_api_network_static_ip(client):
    """Setting static IP works in dev mode."""
    resp = client.post(
        "/api/network",
        data=json.dumps({
            "mode": "static",
            "ip": "192.168.1.50",
            "netmask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns": "8.8.8.8",
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_network_dhcp(client):
    """Setting DHCP mode works in dev mode."""
    resp = client.post(
        "/api/network",
        data=json.dumps({"mode": "dhcp"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


# --- API: Setup ---

def test_api_setup_complete(client, clean_setup_flag):
    """Setup complete API succeeds when flag does not exist."""
    import tempfile
    flag = os.path.join(tempfile.gettempdir(), "harbouros-setup-complete")
    if os.path.exists(flag):
        os.remove(flag)
    resp = client.post("/api/setup/complete")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_api_setup_complete_replay(client):
    """Setup complete API rejects replay when flag already exists."""
    resp = client.post("/api/setup/complete")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "already" in data["error"].lower()
