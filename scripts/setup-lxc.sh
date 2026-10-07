#!/usr/bin/env bash
# Bootstraps a fresh Debian 12 LXC on Proxmox into the fleet-ansible control node
set -euo pipefail

echo "==> Updating package indices and installing prerequisites..."
apt-get update
apt-get install -y --no-install-recommends \
  python3 \
  python3-venv \
  python3-pip \
  git \
  curl \
  jq \
  openssh-client \
  sshpass \
  ca-certificates

echo "==> Installing uv and ansible..."
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
uv tool install --force ansible-core
uv pip install --system requests proxmoxer

echo "==> Configuring /etc/fleet directory for credentials..."
mkdir -p /etc/fleet
if [ ! -f /etc/fleet/openbao.env ]; then
  cat << 'EOF' > /etc/fleet/openbao.env
# OpenBao connection settings for fleet-ansible
OPENBAO_URL=https://secrets.int.spoutin.org
OPENBAO_ROLE_ID=92ac0442-cc8b-779b-bee1-58b45fb66ddc
OPENBAO_SECRET_ID=
EOF
  chmod 600 /etc/fleet/openbao.env
  echo "Created /etc/fleet/openbao.env - please fill in OPENBAO_SECRET_ID."
fi

echo "==> Ansible control node setup complete!"
echo "Next steps:"
echo "1. Set OPENBAO_SECRET_ID in /etc/fleet/openbao.env"
echo "2. Clone fleet-ansible into /opt/fleet-ansible"
echo "3. Run: ansible-playbook playbooks/renew-controller-cert.yml"
echo "4. Run: ansible-playbook playbooks/bootstrap.yml"
