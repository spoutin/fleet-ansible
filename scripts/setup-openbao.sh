#!/usr/bin/env bash
# Helper script to set up OpenBao AppRole and fleet secrets for fleet-ansible
set -euo pipefail

OPENBAO_ADDR="${OPENBAO_ADDR:-http://10.0.0.29:8200}"

echo "Configuring OpenBao for fleet-ansible on $OPENBAO_ADDR..."

# 1. Upload policy
bao policy write fleet-ansible - << 'EOF'
path "secret/data/fleet" {
  capabilities = ["read"]
}
path "ssh/config/ca" {
  capabilities = ["read"]
}
path "ssh/public_key" {
  capabilities = ["read"]
}
path "ssh/sign/operator-user" {
  capabilities = ["create", "update"]
}
path "ssh/sign/admin-user" {
  capabilities = ["create", "update"]
}
EOF

# 2. Configure AppRole
bao write auth/approle/role/fleet-ansible \
  token_policies="fleet-ansible" \
  token_ttl=1h \
  token_max_ttl=24h

ROLE_ID=$(bao read -field=role_id auth/approle/role/fleet-ansible/role-id)
SECRET_ID=$(bao write -field=secret_id -f auth/approle/role/fleet-ansible/secret-id)

echo "================================================="
echo "OpenBao AppRole configured for fleet-ansible!"
echo "ROLE_ID:   $ROLE_ID"
echo "SECRET_ID: $SECRET_ID"
echo "================================================="
echo "Add these to /etc/fleet/openbao.env on the Ansible LXC container."
