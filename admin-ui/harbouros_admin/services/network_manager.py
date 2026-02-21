"""Network configuration service."""

import os
import socket
import subprocess

import psutil

DHCPCD_CONF = "/etc/dhcpcd.conf"


def _run(cmd):
    """Run a command and return stdout."""
    if os.environ.get("HARBOUROS_DEV"):
        return _mock_run(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else ""


def _mock_run(cmd):
    """Return mock responses for dev mode."""
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    if "hostname" in cmd_str:
        return "harbouros"
    if "ip route" in cmd_str:
        return "default via 192.168.1.1 dev eth0"
    return ""


def get_ip_mode():
    """Determine if the current config is static or DHCP."""
    if os.environ.get("HARBOUROS_DEV"):
        return "dhcp"
    try:
        with open(DHCPCD_CONF) as f:
            content = f.read()
        if "static ip_address=" in content:
            return "static"
    except FileNotFoundError:
        pass
    return "dhcp"


def get_network_info():
    """Get current network configuration."""
    hostname = socket.gethostname()

    # Find the primary network interface and IP
    ip_address = None
    interface = None
    for name, addrs in psutil.net_if_addrs().items():
        if name in ("lo", "lo0"):
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                ip_address = addr.address
                interface = name
                break
        if ip_address:
            break

    # Get gateway
    gateway = None
    route_output = _run(["ip", "route", "show", "default"])
    if route_output:
        parts = route_output.split()
        if len(parts) >= 3:
            gateway = parts[2]

    # Get DNS servers
    dns_servers = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                if line.strip().startswith("nameserver"):
                    dns_servers.append(line.strip().split()[1])
    except FileNotFoundError:
        pass

    return {
        "hostname": hostname,
        "ip_address": ip_address or "unknown",
        "interface": interface or "unknown",
        "gateway": gateway,
        "dns_servers": dns_servers,
        "mode": get_ip_mode(),
    }


def set_hostname(new_hostname):
    """Update the system hostname."""
    if os.environ.get("HARBOUROS_DEV"):
        return True, f"Hostname would be set to: {new_hostname}"

    result = subprocess.run(
        ["hostnamectl", "set-hostname", new_hostname],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return True, f"Hostname set to {new_hostname}"
    return False, result.stderr.strip()


def set_network_config(mode, interface="eth0", ip=None, netmask=None,
                       gateway=None, dns=None):
    """Set network to static or DHCP mode via dhcpcd.conf."""
    if os.environ.get("HARBOUROS_DEV"):
        if mode == "static":
            return True, f"Would set {interface} to static IP {ip} (dev mode)"
        return True, f"Would set {interface} to DHCP (dev mode)"

    try:
        with open(DHCPCD_CONF) as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    # Remove existing static block for this interface
    cleaned = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == f"interface {interface}":
            skip = True
            continue
        if skip and (stripped.startswith("static ") or
                     stripped.startswith("domain_name_servers")):
            continue
        if skip and stripped == "":
            skip = False
            continue
        skip = False
        cleaned.append(line)

    if mode == "static":
        if not all([ip, netmask, gateway]):
            return False, "Static mode requires ip, netmask, and gateway"
        prefix = sum(bin(int(x)).count("1") for x in netmask.split("."))
        block = (
            f"\ninterface {interface}\n"
            f"static ip_address={ip}/{prefix}\n"
            f"static routers={gateway}\n"
        )
        if dns:
            block += f"static domain_name_servers={dns}\n"
        cleaned.append(block)

    with open(DHCPCD_CONF, "w") as f:
        f.writelines(cleaned)

    return True, "Network configuration updated. You may need to reconnect at the new IP."
