#!/usr/bin/env bash
set -euo pipefail

# Sourced parse_target test
source <(grep -A 25 'parse_target()' bin/fleet-ansible)

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

echo "All CLI argument tests passed successfully!"
