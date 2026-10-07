#!/usr/bin/env python3
"""
LAN-Orangutan Dynamic Inventory Script for Ansible

Fetches inventory dynamically from LAN-Orangutan (https://github.com/spoutin/LAN-Orangutan)
and OpenBao KV v2 secrets engine.

Zero external dependencies - uses standard library Python 3 modules only.

Filters strictly for hosts where `ansible_managed: true` has been enabled (either
automatically by port 22 detection or manually via the web UI).
"""

import os
import sys
import json
import argparse
import ssl
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from typing import Dict, Any, Optional

# Disable SSL verification for internal homelab communication
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def load_env_file(filepath: str) -> Dict[str, str]:
    """Load key-value pairs from a simple env file if present."""
    env: Dict[str, str] = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    return env


def get_openbao_secrets() -> Dict[str, Any]:
    """Fetch fleet secrets from OpenBao KV v2 engine."""
    file_env = {}
    for p in ["/etc/fleet/openbao.env", "./openbao.env", "../openbao.env"]:
        if os.path.exists(p):
            file_env = load_env_file(p)
            break

    bao_url = (
        os.getenv("OPENBAO_URL")
        or file_env.get("OPENBAO_URL")
        or "https://secrets.int.spoutin.org"
    ).rstrip("/")
    role_id = os.getenv("OPENBAO_ROLE_ID") or file_env.get("OPENBAO_ROLE_ID") or "92ac0442-cc8b-779b-bee1-58b45fb66ddc"
    secret_id = os.getenv("OPENBAO_SECRET_ID") or file_env.get("OPENBAO_SECRET_ID")
    token = os.getenv("OPENBAO_TOKEN") or file_env.get("OPENBAO_TOKEN")

    # If token not provided directly, authenticate via AppRole
    if not token and role_id and secret_id:
        try:
            login_data = json.dumps({"role_id": role_id, "secret_id": secret_id}).encode("utf-8")
            req = urllib.request.Request(
                f"{bao_url}/v1/auth/approle/login",
                data=login_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5, context=SSL_CTX) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    token = data.get("auth", {}).get("client_token")
        except Exception as e:
            sys.stderr.write(f"Warning: OpenBao AppRole login failed: {e}\n")

    secrets: Dict[str, Any] = {}
    if token:
        try:
            req = urllib.request.Request(
                f"{bao_url}/v1/secret/data/fleet",
                headers={"X-Vault-Token": token},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5, context=SSL_CTX) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    secrets = data.get("data", {}).get("data", {})
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to fetch fleet secrets from OpenBao: {e}\n")

    return secrets


def fetch_orangutan_devices(
    base_url: str, password: Optional[str] = None
) -> Dict[str, Any]:
    """Authenticate to LAN-Orangutan and fetch devices list."""
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=SSL_CTX),
    )

    # Perform login if password is provided
    if password and password != "CHANGE_ME":
        try:
            login_data = urllib.parse.urlencode({"password": password}).encode("utf-8")
            login_req = urllib.request.Request(
                f"{base_url}/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            opener.open(login_req, timeout=5)
        except Exception as e:
            sys.stderr.write(f"Warning: LAN-Orangutan login failed: {e}\n")

    req = urllib.request.Request(f"{base_url}/api/devices", method="GET")
    with opener.open(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            return data["data"]
        elif isinstance(data, dict):
            return data
    return {}


def classify_os_group(device: Dict[str, Any]) -> str:
    """Classify device into an OS group based on vendor, hostname, or custom fields."""
    vendor = (device.get("vendor") or "").lower()
    hostname = (device.get("hostname") or device.get("custom_hostname") or "").lower()
    notes = (device.get("notes") or "").lower()

    if "alpine" in hostname or "alpine" in notes:
        return "alpine"
    if "fedora" in hostname or "rhel" in hostname or "centos" in hostname or "redhat" in notes:
        return "redhat"
    if "ubuntu" in hostname or "ubuntu" in notes or "ubuntu" in vendor:
        return "ubuntu"
    if "proxmox" in hostname or "pve" in hostname or "proxmox" in notes:
        return "proxmox"
    return "debian"


def get_device_base_name(ip: str, dev: Dict[str, Any]) -> str:
    """Generate normalized base name for a device."""
    raw_name = (
        dev.get("label")
        or dev.get("custom_hostname")
        or dev.get("hostname")
        or ip
    )
    return "".join(c if c.isalnum() or c in ".-_" else "_" for c in raw_name)


def find_devices_by_target(query: str, only_managed: bool = True) -> list:
    """Find devices matching a query (by IP, hostname, custom_hostname, or label)."""
    bao_secrets = get_openbao_secrets()
    orangutan_url = (
        os.getenv("ORANGUTAN_URL")
        or bao_secrets.get("orangutan_url")
        or "http://10.0.0.1:291"
    ).rstrip("/")
    orangutan_password = os.getenv("ORANGUTAN_PASSWORD") or bao_secrets.get(
        "orangutan_password"
    )

    try:
        devices = fetch_orangutan_devices(orangutan_url, orangutan_password)
    except Exception:
        return []

    q = query.strip().lower()
    matches = []

    # First pass to compute duplicate counts for consistent naming
    name_counts: Dict[str, int] = {}
    filtered = {}
    for ip, dev in devices.items():
        is_managed = bool(dev.get("ansible_managed", False))
        if only_managed and not is_managed:
            continue
        base_name = get_device_base_name(ip, dev)
        name_counts[base_name] = name_counts.get(base_name, 0) + 1
        filtered[ip] = (dev, base_name)

    for ip, (dev, base_name) in filtered.items():
        host_name = (
            f"{base_name}-{ip.replace('.', '-')}"
            if name_counts[base_name] > 1
            else base_name
        )
        dev_hostname = (dev.get("hostname") or "").lower()
        dev_custom = (dev.get("custom_hostname") or "").lower()
        dev_label = (dev.get("label") or "").lower()

        if (
            ip == q
            or base_name.lower() == q
            or dev_hostname == q
            or dev_custom == q
            or dev_label == q
        ):
            matches.append({
                "ip": ip,
                "name": host_name,
                "base_name": base_name,
                "vendor": dev.get("vendor", "") or "Unknown",
                "label": dev.get("label", ""),
            })

    return matches


def build_inventory(only_managed: bool = True) -> Dict[str, Any]:
    """Construct Ansible inventory JSON."""
    inventory: Dict[str, Any] = {
        "_meta": {"hostvars": {}},
        "all": {"hosts": [], "children": ["ungrouped", "managed_hosts"]},
        "managed_hosts": {"hosts": [], "children": []},
        "debian": {"hosts": [], "vars": {"sshd_service_name": "ssh"}},
        "ubuntu": {"hosts": [], "vars": {"sshd_service_name": "ssh"}},
        "alpine": {"hosts": [], "vars": {"sshd_service_name": "sshd"}},
        "redhat": {"hosts": [], "vars": {"sshd_service_name": "sshd"}},
        "proxmox": {"hosts": [], "vars": {"sshd_service_name": "ssh"}},
        "ungrouped": {"hosts": []},
    }

    # Fetch secrets from OpenBao
    bao_secrets = get_openbao_secrets()

    # Determine LAN-Orangutan URL & Password
    orangutan_url = (
        os.getenv("ORANGUTAN_URL")
        or bao_secrets.get("orangutan_url")
        or "http://10.0.0.1:291"
    ).rstrip("/")
    orangutan_password = os.getenv("ORANGUTAN_PASSWORD") or bao_secrets.get(
        "orangutan_password"
    )

    try:
        devices = fetch_orangutan_devices(orangutan_url, orangutan_password)
    except Exception as e:
        sys.stderr.write(f"Notice: LAN-Orangutan at {orangutan_url} unreachable: {e}\n")
        return inventory

    # First pass: count base_names to detect collisions
    managed_devices = {}
    name_counts: Dict[str, int] = {}
    for ip, dev in devices.items():
        is_managed = bool(dev.get("ansible_managed", False))
        if only_managed and not is_managed:
            continue
        base_name = get_device_base_name(ip, dev)
        name_counts[base_name] = name_counts.get(base_name, 0) + 1
        managed_devices[ip] = (dev, is_managed, base_name)

    for ip, (dev, is_managed, base_name) in managed_devices.items():
        # Disambiguate host key if base_name is shared by multiple devices
        if name_counts[base_name] > 1:
            host_name = f"{base_name}-{ip.replace('.', '-')}"
            # Add base_name as a group containing all duplicates
            if base_name not in inventory:
                inventory[base_name] = {"hosts": []}
                inventory["all"]["children"].append(base_name)
            if host_name not in inventory[base_name]["hosts"]:
                inventory[base_name]["hosts"].append(host_name)
        else:
            host_name = base_name

        hostvars: Dict[str, Any] = {
            "ansible_host": ip,
            "orangutan_ip": ip,
            "orangutan_mac": dev.get("mac", ""),
            "orangutan_vendor": dev.get("vendor", ""),
            "orangutan_label": dev.get("label", ""),
            "ansible_managed": is_managed,
        }

        inventory["_meta"]["hostvars"][host_name] = hostvars
        inventory["all"]["hosts"].append(host_name)
        if is_managed:
            inventory["managed_hosts"]["hosts"].append(host_name)

        os_group = classify_os_group(dev)
        if os_group not in inventory:
            inventory[os_group] = {"hosts": []}
        inventory[os_group]["hosts"].append(host_name)

        # Map IP address as a group alias so `--limit <ip>` targets this host
        if ip not in inventory:
            inventory[ip] = {"hosts": []}
            inventory["all"]["children"].append(ip)
        if host_name not in inventory[ip]["hosts"]:
            inventory[ip]["hosts"].append(host_name)

        custom_group = dev.get("group")
        if custom_group:
            safe_group = "".join(
                c if c.isalnum() or c == "_" else "_" for c in custom_group.lower()
            )
            if safe_group not in inventory:
                inventory[safe_group] = {"hosts": []}
            if host_name not in inventory[safe_group]["hosts"]:
                inventory[safe_group]["hosts"].append(host_name)

    return inventory


def main():
    parser = argparse.ArgumentParser(description="LAN-Orangutan Dynamic Inventory")
    parser.add_argument("--list", action="store_true", help="List all hosts")
    parser.add_argument("--host", help="Get host variables for a specific host")
    parser.add_argument(
        "--find",
        help="Find devices matching a query (by IP, hostname, or label) for disambiguation",
    )
    parser.add_argument(
        "--all-hosts",
        action="store_true",
        help="Include all online devices, ignoring ansible_managed flag",
    )
    args = parser.parse_args()

    if args.find:
        matches = find_devices_by_target(args.find, only_managed=not args.all_hosts)
        print(json.dumps(matches, indent=2))
    elif args.host:
        inv = build_inventory(only_managed=not args.all_hosts)
        print(json.dumps(inv["_meta"]["hostvars"].get(args.host, {}), indent=2))
    else:
        inv = build_inventory(only_managed=not args.all_hosts)
        print(json.dumps(inv, indent=2))


if __name__ == "__main__":
    main()
