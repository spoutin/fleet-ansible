#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CMD="python3"

# Extract helper functions from bin/fleet-ansible
eval "$(sed -n '/^parse_target()/,/^}/p' "$APP_DIR/bin/fleet-ansible")"
eval "$(sed -n '/^resolve_target()/,/^}/p' "$APP_DIR/bin/fleet-ansible")"
eval "$(sed -n '/^cleanup()/,/^}/p' "$APP_DIR/bin/fleet-ansible")"
eval "$(sed -n '/^setup_password_file()/,/^}/p' "$APP_DIR/bin/fleet-ansible")"

test_target() {
    local expected_target="$1"
    local expected_extra="$2"
    shift 2

    parse_target "$@"

    if [ "$TARGET" != "$expected_target" ]; then
        echo "FAIL: Expected target '$expected_target', got '$TARGET'" >&2
        exit 1
    fi

    local extra_str="${EXTRA_ARGS[*]-}"
    if [ "$extra_str" != "$expected_extra" ]; then
        echo "FAIL: Expected extra args '$expected_extra', got '$extra_str'" >&2
        exit 1
    fi
    echo "PASS: $* -> target='$TARGET', extra='$extra_str'"
}

test_target "" ""
test_target "10.0.0.82" "" 10.0.0.82
test_target "10.0.0.82" "-k" 10.0.0.82 -k
test_target "10.0.0.82" "-k -vvv" --limit 10.0.0.82 -k -vvv
test_target "truenas" "" truenas
test_target "hypervisors" "-k" -l hypervisors -k
test_target "debian" "--check" debian --check

# Test resolve_target with IP bypass
TARGET="10.0.0.82"
resolve_target
if [ "$TARGET" != "10.0.0.82" ]; then
    echo "FAIL: resolve_target modified IP target" >&2
    exit 1
fi
echo "PASS: resolve_target bypassed for IP 10.0.0.82"

# Test resolve_target with standard group bypass
TARGET="hypervisors"
resolve_target
if [ "$TARGET" != "hypervisors" ]; then
    echo "FAIL: resolve_target modified hypervisors group" >&2
    exit 1
fi
echo "PASS: resolve_target bypassed for hypervisors"

# Test setup_password_file with ANSIBLE_SSH_PASSWORD
export ANSIBLE_SSH_PASSWORD="test-vault-password"
setup_password_file
if [ -z "${ANSIBLE_CONNECTION_PASSWORD_FILE:-}" ] || [ ! -f "$ANSIBLE_CONNECTION_PASSWORD_FILE" ]; then
    echo "FAIL: setup_password_file failed to create password file" >&2
    exit 1
fi
content="$(cat "$ANSIBLE_CONNECTION_PASSWORD_FILE")"
if [ "$content" != "test-vault-password" ]; then
    echo "FAIL: Password file content mismatch: '$content'" >&2
    exit 1
fi
echo "PASS: setup_password_file created file with correct password"

# Test cleanup removes file
cleanup
if [ -f "$PASS_TMP_FILE" ]; then
    echo "FAIL: cleanup failed to remove password file" >&2
    exit 1
fi
echo "PASS: cleanup removed temporary password file"

# Test bash completion script
source "$APP_DIR/packaging/completion/fleet-ansible"

COMP_WORDS=("fleet-ansible" "in")
COMP_CWORD=1
_fleet_ansible_complete
if [[ "${COMPREPLY[*]}" != *"install-pki"* ]]; then
    echo "FAIL: Bash completion failed to complete install-pki: '${COMPREPLY[*]}'" >&2
    exit 1
fi
echo "PASS: Bash completion completed 'install-pki'"

COMP_WORDS=("fleet-ansible" "ping" "hyp")
COMP_CWORD=2
_fleet_ansible_complete
if [[ "${COMPREPLY[*]}" != *"hypervisors"* ]]; then
    echo "FAIL: Bash completion failed to complete target 'hypervisors': '${COMPREPLY[*]}'" >&2
    exit 1
fi
echo "PASS: Bash completion completed 'hypervisors'"

# Test fleet-ansible completion command
completion_output="$("$APP_DIR/bin/fleet-ansible" completion)"
if [[ "$completion_output" != *"complete -F _fleet_ansible_complete fleet-ansible"* ]]; then
    echo "FAIL: fleet-ansible completion output missing complete directive" >&2
    exit 1
fi
echo "PASS: fleet-ansible completion output valid"

# Source the dynamic completion output and verify 'enroll' is completed
eval "$completion_output"
COMP_WORDS=("fleet-ansible" "en")
COMP_CWORD=1
_fleet_ansible_complete
if [[ "${COMPREPLY[*]}" != *"enroll"* ]]; then
    echo "FAIL: Dynamic completion output failed to complete 'enroll': '${COMPREPLY[*]}'" >&2
    exit 1
fi
echo "PASS: Dynamic completion output successfully completed 'enroll'"

echo "All CLI argument and resolution tests passed successfully!"
