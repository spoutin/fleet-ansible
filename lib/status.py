#!/usr/bin/env python3
"""
Fleet Enrollment & Health Status Reporter

Aggregates inventory from static_hosts.yml and LAN-Orangutan, runs live
parallel SSH checks, and formats a clean, actionable status table.
"""

import os
import sys
import json
import argparse
import subprocess
from typing import Dict, Any, List, Tuple, Optional

# Setup path to import inventory.orangutan
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "inventory"))
from orangutan import (
    fetch_orangutan_devices,
    get_openbao_secrets,
    get_device_base_name,
    classify_os_group,
)


def classify_host_status(check_line: str, is_managed: bool = True) -> Tuple[str, str, str]:
    """Classifies an Ansible probe result into an actionable status code, badge, and detail."""
    if "CA_ENROLLED" in check_line:
        if is_managed:
            return ("ENROLLED", "●", "OK (CA Trust Active)")
        else:
            return ("PAUSED", "⏸", "Enrolled with CA, but toggled OFF in LAN-Orangutan")

    if "KEY_ONLY" in check_line:
        if is_managed:
            return ("KEY_ONLY", "◐", "SSH key verified; PKI not installed")
        else:
            return ("PAUSED", "⏸", "Key authorized, but toggled OFF in LAN-Orangutan")

    if "NO_SUDO" in check_line or "Missing sudo password" in check_line:
        return ("NO_SUDO", "▲", "User 'ansible' lacks passwordless sudo")

    # Fallback / backward-compatibility with ping output
    if "SUCCESS" in check_line and "ping" in check_line:
        if is_managed:
            return ("ENROLLED", "●", "OK (CA / Key Verified)")
        else:
            return ("PAUSED", "⏸", "Enrolled, but toggled OFF in LAN-Orangutan")

    if "Permission denied" in check_line:
        if "(publickey)." in check_line:
            return ("AUTH_ERROR", "✖", "Key rejected & Password auth disabled")
        elif "(publickey,password)" in check_line:
            return ("AUTH_ERROR", "✖", "Key rejected & Password invalid or missing")
        else:
            return ("AUTH_ERROR", "✖", "User 'ansible' missing or rejected")

    if "Connection refused" in check_line:
        return ("OFFLINE", "○", "Port 22 closed / SSH stopped")

    if "timed out" in check_line or "No route to host" in check_line or "unreachable" in check_line.lower():
        return ("OFFLINE", "○", "Host offline / connection timed out")

    detail = check_line.split("=>", 1)[-1].strip() if "=>" in check_line else "Check failed"
    return ("FAILED", "✖", detail[:50])


def load_static_hosts() -> List[Dict[str, Any]]:
    """Loads hypervisors from static_hosts.yml if present."""
    static_file = os.path.join(os.path.dirname(__file__), "..", "inventory", "static_hosts.yml")
    hosts = []
    if os.path.exists(static_file):
        try:
            with open(static_file, "r", encoding="utf-8") as f:
                content = f.read()
            # Simple line parsing to avoid yaml dependency if pyyaml not installed
            current_host = None
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("pve") and stripped.endswith(":"):
                    current_host = stripped.rstrip(":")
                elif current_host and "ansible_host:" in stripped:
                    ip = stripped.split("ansible_host:")[-1].split("#")[0].strip()
                    hosts.append({
                        "name": current_host,
                        "ip": ip,
                        "os": "Proxmox",
                        "source": "static_hosts.yml",
                        "is_managed": True,
                    })
                    current_host = None
        except Exception:
            pass
    if not hosts:
        # Default known hypervisors
        hosts = [
            {"name": "pve1", "ip": "10.0.0.41", "os": "Proxmox", "source": "static_hosts.yml", "is_managed": True},
            {"name": "pve2", "ip": "10.0.0.42", "os": "Proxmox", "source": "static_hosts.yml", "is_managed": True},
        ]
    return hosts


def format_status_table(records: List[Dict[str, Any]], use_color: bool = True) -> str:
    """Renders the status records into a formatted terminal table."""
    if use_color:
        c_reset = "\033[0m"
        c_bold = "\033[1m"
        c_dim = "\033[2m"
        c_green = "\033[0;32m"
        c_cyan = "\033[0;36m"
        c_yellow = "\033[0;33m"
        c_red = "\033[0;31m"
    else:
        c_reset = c_bold = c_dim = c_green = c_cyan = c_yellow = c_red = ""

    lines = []
    lines.append(f"{c_bold}{c_cyan}FLEET ENROLLMENT & HEALTH STATUS{c_reset}")
    lines.append("=" * 110)
    lines.append(f"{c_bold}{'STATUS':<14} {'HOST':<24} {'IP':<16} {'OS / VENDOR':<16} {'DETAILS'}{c_reset}")
    lines.append("=" * 110)

    enrolled = 0
    key_only = 0
    paused = 0
    auth_err = 0
    offline = 0
    no_sudo = 0
    next_steps = []

    for r in records:
        status = r.get("status", "UNKNOWN")
        badge = r.get("badge", "•")
        host = r.get("name", "unknown")
        ip = r.get("ip", "")
        os_vendor = r.get("os", "Linux")
        detail = r.get("detail", "")

        if status == "ENROLLED":
            enrolled += 1
            color = c_green
        elif status == "KEY_ONLY":
            key_only += 1
            color = c_yellow
            next_steps.append(f"  • {c_bold}{host}{c_reset}: SSH key authorized, but CA trust not installed. Run: fleet-ansible install-pki {host}")
        elif status == "PAUSED":
            paused += 1
            color = c_cyan
            next_steps.append(f"  • {c_bold}{host}{c_reset}: Enrolled with CA, but toggled OFF in LAN-Orangutan. Toggle ON in web UI to resume.")
        elif status == "AUTH_ERROR":
            auth_err += 1
            color = c_red
            if "Key rejected" in detail and "disabled" in detail:
                next_steps.append(f"  • {c_bold}{host}{c_reset}: Run 'fleet-ansible show-key' and paste key into user authorized_keys.")
            else:
                next_steps.append(f"  • {c_bold}{host}{c_reset}: Ensure user 'ansible' exists, or run: fleet-ansible install-pki {ip} -k")
        elif status == "NO_SUDO":
            no_sudo += 1
            color = c_yellow
            next_steps.append(f"  • {c_bold}{host}{c_reset}: Add 'ansible ALL=(ALL) NOPASSWD:ALL' to /etc/sudoers.d/ansible.")
        elif status == "OFFLINE":
            offline += 1
            color = c_dim
        elif status == "UNMANAGED":
            color = c_dim
        else:
            color = c_reset

        status_str = f"{badge} {status}"
        lines.append(f"{color}{status_str:<14}{c_reset} {host:<24} {ip:<16} {os_vendor:<16} {c_dim}{detail}{c_reset}")

    lines.append("=" * 110)
    summary_parts = []
    if enrolled:
        summary_parts.append(f"{c_green}{enrolled} Enrolled{c_reset}")
    if key_only:
        summary_parts.append(f"{c_yellow}{key_only} Key Only{c_reset}")
    if paused:
        summary_parts.append(f"{c_cyan}{paused} Paused{c_reset}")
    if auth_err:
        summary_parts.append(f"{c_red}{auth_err} Auth Errors{c_reset}")
    if no_sudo:
        summary_parts.append(f"{c_yellow}{no_sudo} No Sudo{c_reset}")
    if offline:
        summary_parts.append(f"{c_dim}{offline} Offline{c_reset}")

    summary_str = ", ".join(summary_parts) if summary_parts else "0 hosts"
    lines.append(f"{c_bold}Summary:{c_reset} {summary_str} | Total: {len(records)} hosts")

    if next_steps:
        lines.append("")
        lines.append(f"{c_bold}{c_yellow}Next Steps for Inactive Hosts:{c_reset}")
        lines.extend(next_steps)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fleet Enrollment & Health Status")
    parser.add_argument("target", nargs="?", help="Optional target host, IP, or group")
    parser.add_argument("--all", action="store_true", help="Include unmanaged LAN devices")
    parser.add_argument("--no-ping", action="store_true", help="Skip live SSH check and display inventory metadata")
    args = parser.parse_args()

    use_color = sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb" and not os.environ.get("NO_COLOR")

    # 1. Collect inventory hosts
    hosts_dict = {}
    for sh in load_static_hosts():
        hosts_dict[sh["ip"]] = sh

    bao_secrets = get_openbao_secrets()
    orangutan_url = (os.getenv("ORANGUTAN_URL") or bao_secrets.get("orangutan_url") or "http://10.0.0.1:291").rstrip("/")
    orangutan_password = os.getenv("ORANGUTAN_PASSWORD") or bao_secrets.get("orangutan_password")

    try:
        devices = fetch_orangutan_devices(orangutan_url, orangutan_password)
        for ip, dev in devices.items():
            is_managed = bool(dev.get("ansible_managed", False))
            if not args.all and not is_managed and ip not in hosts_dict:
                continue

            base_name = get_device_base_name(ip, dev)
            os_name = classify_os_group(dev).capitalize()
            vendor = dev.get("vendor", "")
            display_os = os_name if os_name != "Debian" or not vendor else vendor

            if ip in hosts_dict:
                hosts_dict[ip]["is_managed"] = is_managed or hosts_dict[ip]["is_managed"]
            else:
                hosts_dict[ip] = {
                    "name": base_name,
                    "ip": ip,
                    "os": display_os,
                    "source": "LAN-Orangutan",
                    "is_managed": is_managed,
                }
    except Exception:
        pass

    target_list = list(hosts_dict.values())
    if args.target:
        q = args.target.strip().lower()
        target_list = [h for h in target_list if h["ip"] == q or h["name"].lower() == q or q in h["name"].lower()]

    if not target_list:
        print(f"No hosts found matching '{args.target}'" if args.target else "No managed hosts found in inventory.")
        return

    # Sort by IP address numerically
    def ip_key(h):
        try:
            return [int(p) for p in h["ip"].split(".")]
        except Exception:
            return [999, 999, 999, 999]
    target_list.sort(key=ip_key)

    # 2. Perform live check if not disabled
    ping_results = {}
    if not args.no_ping:
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        ansible_cmd = os.path.join(app_dir, ".venv/bin/ansible")
        if not os.path.exists(ansible_cmd):
            ansible_cmd = "ansible"

        # Build comma-separated targets
        target_ips = ",".join(h["ip"] for h in target_list) + ","
        probe_cmd = (
            "sh -c 'CA=0; SUDO=0; test -f /etc/ssh/trusted-user-ca-keys.pub && CA=1; "
            "(command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null) && SUDO=1; "
            "if [ \"$SUDO\" = \"0\" ]; then echo NO_SUDO; elif [ \"$CA\" = \"1\" ]; then echo CA_ENROLLED; else echo KEY_ONLY; fi'"
        )
        try:
            res = subprocess.run(
                [ansible_cmd, "-i", target_ips, "all", "-m", "command", "-a", probe_cmd, "-o"],
                capture_output=True,
                text=True,
                timeout=25,
            )
            for line in (res.stdout + "\n" + res.stderr).splitlines():
                if "|" in line:
                    ip_match = line.split("|")[0].strip()
                    ping_results[ip_match] = line
        except Exception as e:
            sys.stderr.write(f"Notice: Live check failed to run: {e}\n")

    # 3. Classify each host
    records = []
    for h in target_list:
        ip = h["ip"]
        is_managed = h.get("is_managed", True)
        if args.no_ping:
            status = "ENROLLED" if is_managed else "UNMANAGED"
            badge = "●" if is_managed else "·"
            detail = "Managed in inventory (check skipped)" if is_managed else "Unmanaged in inventory"
        else:
            line = ping_results.get(ip, "")
            if line:
                status, badge, detail = classify_host_status(line, is_managed=is_managed)
            else:
                status = "OFFLINE"
                badge = "○"
                detail = "Host unreachable or offline"

        records.append({
            "status": status,
            "badge": badge,
            "name": h["name"],
            "ip": ip,
            "os": h["os"],
            "detail": detail,
        })

    print(format_status_table(records, use_color=use_color))


if __name__ == "__main__":
    main()
