# fleet-ansible

Automated fleet management and OpenSSH Certificate Authority trust deployment for the Spoutin Homelab.

Controls which machines receive SSH CA trust and configuration based on the **`ansible_managed`** flag in **[LAN-Orangutan](https://github.com/spoutin/LAN-Orangutan)**, stores secrets securely in **OpenBao**, and leverages a **hybrid bootstrap** (Proxmox host-level zero-SSH injection followed by network SSH fallback).

---

## Architecture

```text
                                 +-----------------------+
                                 |  OpenBao (10.0.0.29)  |
                                 |  - secret/data/fleet  |
                                 |  - ssh/public_key     |
                                 +-----------------------+
                                        ^         ^
                  Orangutan & SSH PW    |         |  AppRole / CA Key
                                        v         |
     +--------------------------+    +------------------------------------+
     |      LAN-Orangutan       |    |       fleet-ansible (LXC)          |
     |  - Port 22 auto-detect   |    |                                    |
     |  - ansible_managed toggle|<---| 1. inventory/orangutan.py (dynamic)|
     +--------------------------+    +------------------------------------+
                                                     |
                         +---------------------------+---------------------------+
                         | (Hybrid Step 1: Zero-SSH)                             | (Hybrid Step 2: SSH Fallback)
                         v                                                       v
            +-------------------------+                             +-------------------------+
            |  Proxmox Hypervisors    |                             | Bare Metal / Non-Agent  |
            |  - pct push/exec (LXCs) |                             | - Admin keys or OpenBao |
            |  - qm guest exec (VMs)  |                             |   fallback password     |
            +-------------------------+                             +-------------------------+
                         |                                                       |
                         +---------------------------+---------------------------+
                                                     |
                                                     v
                                       +---------------------------+
                                       |   All Target Machines     |
                                       |  - trusted-user-ca-keys   |
                                       |  - sshd_config.d/60-pki   |
                                       +---------------------------+
```

---

## Key Features

1. **LAN-Orangutan Driven (`ansible_managed`)**:
   - Only hosts with `ansible_managed: true` in LAN-Orangutan are targeted by Ansible.
   - When LAN-Orangutan detects an active machine with Port 22 open, it automatically enables `ansible_managed: true` by default.
   - You can toggle the flag on or off anytime via the LAN-Orangutan web dashboard.

2. **Zero-Secret Local Storage (OpenBao KV v2)**:
   - Credentials (LAN-Orangutan password, fallback SSH passwords) live in OpenBao at `secret/data/fleet`.
   - The Ansible LXC controller connects via an AppRole (`fleet-ansible`) defined in `/etc/fleet/openbao.env`.

3. **Hybrid Passwordless Bootstrap**:
   - **Phase 1 (Proxmox Host Injection)**: Directly pushes `/etc/ssh/trusted-user-ca-keys.pub` and `/etc/ssh/sshd_config.d/60-pki-ssh-ca.conf` into LXCs (`pct push`/`pct exec`) and VMs (`qm guest exec`). No guest passwords or keys needed!
   - **Phase 2 (Network SSH Fallback)**: Targets any remaining bare-metal or non-virtualized nodes using existing SSH keys or OpenBao's fallback password.

4. **Self-Certifying Controller**:
   - The Ansible LXC controller signs its own Ed25519 key against the OpenBao SSH CA (`playbooks/renew-controller-cert.yml`) with principals `operator,root`.
   - All subsequent Ansible runs authenticate across the fleet using SSH certificates.

---

## Directory Layout

```text
fleet-ansible/
├── ansible.cfg                    # Strict SSH settings, pipelining, inventory pointer
├── inventory/
│   ├── orangutan.py               # Dynamic inventory script (OpenBao -> LAN-Orangutan)
│   ├── static_hosts.yml           # Proxmox hypervisors and static infrastructure
│   └── group_vars/
│       ├── all.yml                # CA public key URLs and drop-in file paths
│       ├── debian.yml             # sshd service: ssh
│       ├── ubuntu.yml             # sshd service: ssh
│       ├── alpine.yml             # sshd service: sshd (OpenRC)
│       └── redhat.yml             # sshd service: sshd
├── playbooks/
│   ├── bootstrap.yml              # Hybrid rollout (Proxmox push -> SSH fallback)
│   ├── renew-controller-cert.yml  # Signs/renews the Ansible LXC's own certificate
│   └── site.yml                   # Routine fleet-wide configuration
├── roles/
│   ├── proxmox_bootstrap/         # Executes pct/qm push & exec from hypervisors
│   └── ssh_ca_client/             # In-guest sshd CA configuration & safety handlers
└── scripts/
    ├── setup-lxc.sh               # Bootstraps the Debian 12 Ansible LXC
    └── setup-openbao.sh           # Seeds OpenBao secret/data/fleet & AppRole
```

---

## Quickstart

### 1. Provision the Ansible Control LXC
On Proxmox, create a lightweight Debian 12 container, copy `scripts/setup-lxc.sh`, and run it:
```bash
bash scripts/setup-lxc.sh
```

### 2. Configure OpenBao Credentials on the LXC
Edit `/etc/fleet/openbao.env`:
```ini
OPENBAO_URL=http://10.0.0.29:8200
OPENBAO_ROLE_ID=92ac0442-cc8b-779b-bee1-58b45fb66ddc
OPENBAO_SECRET_ID=<your-secret-id>
```

### 3. Issue the Controller's SSH Certificate
```bash
ansible-playbook playbooks/renew-controller-cert.yml
```

### 4. Run the Hybrid Bootstrap
```bash
ansible-playbook playbooks/bootstrap.yml
```

### 5. Routine Maintenance
To update or verify CA trust across all managed hosts:
```bash
ansible-playbook playbooks/site.yml
```
