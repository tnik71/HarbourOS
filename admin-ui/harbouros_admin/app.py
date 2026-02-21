"""HarbourOS Admin UI — Flask application."""

import os
import time
from collections import defaultdict
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from .services import (
    auth_service,
    mount_manager,
    network_manager,
    plex_service,
    system_info,
)

SETUP_FLAG = "/etc/harbouros/.setup-complete"
if os.environ.get("HARBOUROS_DEV"):
    import tempfile
    SETUP_FLAG = os.path.join(tempfile.gettempdir(), "harbouros-setup-complete")


_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60
_login_attempts = defaultdict(list)


def _is_rate_limited(ip):
    """Check if an IP has exceeded the login attempt limit."""
    now = time.time()
    attempts = _login_attempts[ip]
    # Prune old attempts
    _login_attempts[ip] = [t for t in attempts if now - t < _WINDOW_SECONDS]
    return len(_login_attempts[ip]) >= _MAX_ATTEMPTS


def _record_attempt(ip):
    """Record a failed login attempt."""
    _login_attempts[ip].append(time.time())


def create_app():
    app = Flask(__name__)
    app.secret_key = auth_service.get_or_create_secret_key()

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Allow access during initial setup (before first-boot wizard completes)
            if not os.path.exists(SETUP_FLAG):
                return f(*args, **kwargs)
            if not session.get("authenticated"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Authentication required"}), 401
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return decorated

    # --- Authentication ---

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")
        ip = request.remote_addr or "unknown"
        if _is_rate_limited(ip):
            return jsonify({"success": False, "error": "Too many attempts. Try again later."}), 429
        data = request.get_json(silent=True) or {}
        password = data.get("password", "")
        if auth_service.verify_password(password):
            _login_attempts.pop(ip, None)
            session["authenticated"] = True
            return jsonify({"success": True})
        _record_attempt(ip)
        return jsonify({"success": False, "error": "Invalid password"}), 401

    @app.route("/api/auth/logout", methods=["POST"])
    def logout():
        session.clear()
        return jsonify({"success": True})

    @app.route("/api/auth/status")
    def auth_status():
        return jsonify({
            "authenticated": bool(session.get("authenticated")),
            "password_changed": auth_service.is_password_changed(),
        })

    # --- Page Routes ---

    @app.route("/")
    @login_required
    def dashboard():
        if not os.path.exists(SETUP_FLAG):
            return render_template("setup.html")
        return render_template("dashboard.html")

    @app.route("/nas")
    @login_required
    def nas():
        return render_template("dashboard.html")

    @app.route("/plex")
    @login_required
    def plex():
        return render_template("dashboard.html")

    @app.route("/network")
    @login_required
    def network():
        return render_template("dashboard.html")

    @app.route("/setup")
    def setup():
        return render_template("setup.html")

    # --- API: System ---

    @app.route("/api/system/status")
    @login_required
    def api_system_status():
        return jsonify(system_info.get_system_status())

    @app.route("/api/system/power", methods=["POST"])
    @login_required
    def api_system_power():
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        if action not in ("shutdown", "reboot"):
            return jsonify({"error": "Action must be 'shutdown' or 'reboot'"}), 400
        success, message = system_info.power_action(action)
        return jsonify({"success": success, "message": message})

    @app.route("/api/system/logs")
    @login_required
    def api_system_logs():
        service = request.args.get("service", "all")
        lines = request.args.get("lines", 100, type=int)
        logs = system_info.get_system_logs(service, lines)
        return jsonify({"logs": logs})

    @app.route("/api/system/services")
    @login_required
    def api_system_services():
        return jsonify({"services": system_info.get_service_statuses()})

    @app.route("/api/system/update/status")
    @login_required
    def api_update_status():
        return jsonify(system_info.check_updates())

    @app.route("/api/system/update", methods=["POST"])
    @login_required
    def api_run_update():
        success, output = system_info.run_update()
        status_code = 200 if success else 500
        return jsonify({"success": success, "output": output}), status_code

    @app.route("/api/system/disk")
    @login_required
    def api_disk_details():
        return jsonify(system_info.get_disk_details())

    @app.route("/api/system/password", methods=["POST"])
    @login_required
    def api_change_password():
        data = request.get_json(silent=True) or {}
        current = data.get("current", "")
        new_pw = data.get("new", "")
        if not current or not new_pw:
            return jsonify({"error": "Both 'current' and 'new' fields required"}), 400
        success, message = auth_service.change_password(current, new_pw)
        status_code = 200 if success else 400
        return jsonify({"success": success, "message": message}), status_code

    # --- API: Plex ---

    @app.route("/api/plex/status")
    @login_required
    def api_plex_status():
        return jsonify(plex_service.get_status())

    @app.route("/api/plex/action", methods=["POST"])
    @login_required
    def api_plex_action():
        data = request.get_json(silent=True) or {}
        action_name = data.get("action")
        if not action_name:
            return jsonify({"error": "Missing 'action' field"}), 400
        success, message = plex_service.action(action_name)
        status_code = 200 if success else 500
        return jsonify({"success": success, "message": message}), status_code

    @app.route("/api/plex/logs")
    @login_required
    def api_plex_logs():
        lines = request.args.get("lines", 50, type=int)
        return jsonify({"logs": plex_service.get_logs(lines)})

    @app.route("/api/plex/update-log")
    @login_required
    def api_plex_update_log():
        return jsonify({"logs": system_info.get_plex_update_log()})

    @app.route("/api/plex/check-update", methods=["POST"])
    @login_required
    def api_plex_check_update():
        if os.environ.get("HARBOUROS_DEV"):
            return jsonify({"success": True, "message": "Update check triggered (dev mode)"})
        import subprocess
        result = subprocess.run(
            ["/usr/local/bin/harbouros-plex-update.sh"],
            capture_output=True, text=True, timeout=120
        )
        return jsonify({
            "success": result.returncode == 0,
            "message": result.stdout.strip(),
        })

    @app.route("/api/plex/libraries")
    @login_required
    def api_plex_libraries():
        return jsonify(plex_service.get_libraries())

    # --- API: Mounts ---

    @app.route("/api/mounts")
    @login_required
    def api_list_mounts():
        return jsonify({"mounts": mount_manager.list_mounts()})

    @app.route("/api/mounts", methods=["POST"])
    @login_required
    def api_add_mount():
        data = request.get_json(silent=True) or {}
        required = ["name", "type", "host", "share"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
        if data["type"] not in ("nfs", "smb"):
            return jsonify({"error": "Type must be 'nfs' or 'smb'"}), 400

        mount = mount_manager.add_mount(
            name=data["name"],
            mount_type=data["type"],
            host=data["host"],
            share=data["share"],
            username=data.get("username"),
            password=data.get("password"),
            domain=data.get("domain"),
            options=data.get("options"),
        )
        return jsonify({"mount": mount}), 201

    @app.route("/api/mounts/<mount_id>", methods=["PUT"])
    @login_required
    def api_update_mount(mount_id):
        data = request.get_json(silent=True) or {}
        mount = mount_manager.update_mount(mount_id, **data)
        if mount is None:
            return jsonify({"error": "Mount not found"}), 404
        return jsonify({"mount": mount})

    @app.route("/api/mounts/<mount_id>", methods=["DELETE"])
    @login_required
    def api_remove_mount(mount_id):
        success = mount_manager.remove_mount(mount_id)
        if not success:
            return jsonify({"error": "Mount not found"}), 404
        return jsonify({"success": True})

    @app.route("/api/mounts/<mount_id>/mount", methods=["POST"])
    @login_required
    def api_mount_share(mount_id):
        success, message = mount_manager.mount_share(mount_id)
        status_code = 200 if success else 500
        return jsonify({"success": success, "message": message}), status_code

    @app.route("/api/mounts/<mount_id>/unmount", methods=["POST"])
    @login_required
    def api_unmount_share(mount_id):
        success, message = mount_manager.unmount_share(mount_id)
        status_code = 200 if success else 500
        return jsonify({"success": success, "message": message}), status_code

    @app.route("/api/mounts/test", methods=["POST"])
    @login_required
    def api_test_connection():
        data = request.get_json(silent=True) or {}
        host = data.get("host")
        mount_type = data.get("type", "nfs")
        if not host:
            return jsonify({"error": "Missing 'host' field"}), 400
        success, message = mount_manager.test_connection(host, mount_type)
        return jsonify({"success": success, "message": message})

    @app.route("/api/mounts/discover")
    @login_required
    def api_discover_devices():
        devices = mount_manager.discover_devices()
        return jsonify({"devices": devices})

    @app.route("/api/mounts/discover/shares", methods=["POST"])
    @login_required
    def api_discover_shares():
        data = request.get_json(silent=True) or {}
        host = data.get("host")
        share_type = data.get("type", "nfs")
        if not host:
            return jsonify({"error": "Missing 'host' field"}), 400
        if share_type not in ("nfs", "smb"):
            return jsonify({"error": "Type must be 'nfs' or 'smb'"}), 400
        shares = mount_manager.discover_shares(
            host, share_type,
            username=data.get("username"),
            password=data.get("password"),
        )
        return jsonify({"shares": shares})

    # --- API: Network ---

    @app.route("/api/network")
    @login_required
    def api_network_info():
        return jsonify(network_manager.get_network_info())

    @app.route("/api/network", methods=["POST"])
    @login_required
    def api_update_network():
        data = request.get_json(silent=True) or {}
        hostname = data.get("hostname")
        mode = data.get("mode")

        if hostname:
            success, message = network_manager.set_hostname(hostname)
            return jsonify({"success": success, "message": message})

        if mode:
            success, message = network_manager.set_network_config(
                mode=mode,
                interface=data.get("interface", "eth0"),
                ip=data.get("ip"),
                netmask=data.get("netmask"),
                gateway=data.get("gateway"),
                dns=data.get("dns"),
            )
            return jsonify({"success": success, "message": message})

        return jsonify({"error": "No changes specified"}), 400

    # --- API: Setup ---

    @app.route("/api/setup/complete", methods=["POST"])
    def api_setup_complete():
        if os.path.exists(SETUP_FLAG):
            return jsonify({"error": "Setup already completed"}), 400
        try:
            os.makedirs(os.path.dirname(SETUP_FLAG), exist_ok=True)
            with open(SETUP_FLAG, "w") as f:
                f.write("1")
            return jsonify({"success": True})
        except OSError as e:
            return jsonify({"error": str(e)}), 500

    return app


app = create_app()
