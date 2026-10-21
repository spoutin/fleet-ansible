# Fleet Automation Roadmap & TODO

Future enhancements and architectural extensions for `fleet-ansible`.

---

## 1. Major Distribution Upgrades
- **Scope**: Support full release upgrades across distributions (e.g., Debian 12 `bookworm` -> Debian 13 `trixie`, Ubuntu LTS upgrades via `do-release-upgrade`, and Rocky/CentOS major leaps).
- **Considerations**:
  - Requires pre-upgrade sanity checks (disk space in `/boot` and `/`, configuration file diffs, broken third-party apt repositories).
  - Post-upgrade validation and potential multi-stage reboots.
  - Snapshot integration (ZFS / Proxmox snapshot before upgrading).

---

## 2. Coordinated Hypervisor Rolling Maintenance
- **Scope**: Coordinated updates and reboot orchestration across Proxmox VE hypervisors (`pve1`, `pve2`).
- **Considerations**:
  - Live VM and LXC migration / evacuation to neighboring nodes before rebooting a host.
  - Node fencing / quorum preservation during restarts.
  - Health checks verifying Proxmox cluster state (`pvecm status`, Ceph health if applicable) before proceeding to the next hypervisor node.

---

## 3. Check / Dry-Run Mode
- **Scope**: Add `--check` / `--dry-run` flag to `fleet-ansible update-os` to preview available package updates without applying changes.
- **Considerations**:
  - Query `apt-get -s dist-upgrade`, `apk upgrade --simulate`, or `dnf check-update`.
  - Format pending updates cleanly in CLI output.
  - Report packages that would trigger a reboot requirement without mutating system state.

---

## 4. TrueNAS Appliance System Updates
- **Scope**: Orchestrate TrueNAS SCALE updates via TrueNAS middleware API (`midclt call update.update` / `update.check_available`).
- **Considerations**:
  - TrueNAS SCALE is an appliance with read-only root system integrity; package managers like `apt` must never be run directly.
  - Coordinate ZFS pool scrub checks and SMB/NFS client connection drains prior to update and reboot.
  - Query update trains and train switching via `midclt call update.get_trains`.
