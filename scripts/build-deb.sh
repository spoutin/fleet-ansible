#!/usr/bin/env bash
set -euo pipefail

# Script to assemble fleet-ansible Debian (.deb) package
VERSION="${1:-0.4.3}"
ARCH="${2:-amd64}"

# Strip leading 'v' from version if present
VERSION="${VERSION#v}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
STAGING_DIR="${REPO_ROOT}/build/deb-staging"

echo "=== Building fleet-ansible package v${VERSION} (${ARCH}) ==="

# Clean staging directory
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}/DEBIAN"
mkdir -p "${STAGING_DIR}/opt/fleet-ansible"
mkdir -p "${STAGING_DIR}/usr/local/bin"
mkdir -p "${STAGING_DIR}/etc/fleet"
mkdir -p "${STAGING_DIR}/lib/systemd/system"
mkdir -p "${DIST_DIR}"

# 1. Prepare DEBIAN control and maintainer scripts
cp -r "${REPO_ROOT}/packaging/deb/DEBIAN/"* "${STAGING_DIR}/DEBIAN/"
sed -i.bak "s/^Version:.*/Version: ${VERSION}/" "${STAGING_DIR}/DEBIAN/control"
sed -i.bak "s/^Architecture:.*/Architecture: ${ARCH}/" "${STAGING_DIR}/DEBIAN/control"
rm -f "${STAGING_DIR}/DEBIAN/"*.bak
chmod 755 "${STAGING_DIR}/DEBIAN/postinst" "${STAGING_DIR}/DEBIAN/prerm"

# 2. Stage application files in /opt/fleet-ansible
echo "Staging fleet-ansible application files..."
cp "${REPO_ROOT}/ansible.cfg" "${STAGING_DIR}/opt/fleet-ansible/"
cp "${REPO_ROOT}/README.md" "${STAGING_DIR}/opt/fleet-ansible/"
cp -r "${REPO_ROOT}/inventory" "${STAGING_DIR}/opt/fleet-ansible/"
cp -r "${REPO_ROOT}/playbooks" "${STAGING_DIR}/opt/fleet-ansible/"
cp -r "${REPO_ROOT}/roles" "${STAGING_DIR}/opt/fleet-ansible/"

# Clean any cache files in staging
find "${STAGING_DIR}/opt/fleet-ansible" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${STAGING_DIR}/opt/fleet-ansible" -name "*.pyc" -delete 2>/dev/null || true
chmod 755 "${STAGING_DIR}/opt/fleet-ansible/inventory/orangutan.py"

# 3. Stage CLI binary
cp "${REPO_ROOT}/bin/fleet-ansible" "${STAGING_DIR}/usr/local/bin/"
chmod 755 "${STAGING_DIR}/usr/local/bin/fleet-ansible"

# 4. Stage configuration example
cp "${REPO_ROOT}/config/openbao.env.example" "${STAGING_DIR}/etc/fleet/"

# 5. Stage systemd units
cp "${REPO_ROOT}/packaging/systemd/"* "${STAGING_DIR}/lib/systemd/system/"

# 6. Build .deb package
OUTPUT_DEB="${DIST_DIR}/fleet-ansible_${VERSION}_${ARCH}.deb"

if command -v dpkg-deb >/dev/null 2>&1; then
    echo "Building Debian package with dpkg-deb..."
    dpkg-deb --build --root-owner-group "${STAGING_DIR}" "${OUTPUT_DEB}"
else
    echo "dpkg-deb not found locally; staging directory created at ${STAGING_DIR}"
    echo "In CI/CD, dpkg-deb will assemble the package into ${OUTPUT_DEB}"
    exit 0
fi

echo "Successfully built: ${OUTPUT_DEB}"
