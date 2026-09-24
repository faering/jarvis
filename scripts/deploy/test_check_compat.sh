#!/usr/bin/env bash
# Tests for scripts/deploy/check-compat.sh.
# Usage: scripts/deploy/test_check_compat.sh   (exits non-zero on any failure)
set -euo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/check-compat.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/compat.json" <<'JSON'
{
  "known_good": [{ "agent": "2.0.0", "app": "1.0.0" }],
  "blocked": [{ "agent": "1.1.0", "app": "1.0.0" }]
}
JSON
echo '{}' >"$tmp/empty.json"
echo '{ "blocked": [' >"$tmp/broken.json"
echo '{ "blocked": {"agent": "1.1.0"} }' >"$tmp/wrong-shape.json"

pass=0
fail=0
check() { # check <name> <expected-exit> <args...>
  local name="$1" want="$2" got=0
  shift 2
  "$script" "$@" >/dev/null 2>&1 || got=$?
  if [[ "$got" == "$want" ]]; then
    pass=$((pass + 1))
    echo "ok   - $name"
  else
    fail=$((fail + 1))
    echo "FAIL - $name: expected exit $want, got $got"
  fi
}

c="$tmp/compat.json"
check "other not deployed" 0 "$c" agent 1.0.0 3 "" ""
check "same protocol (agent)" 0 "$c" agent 1.2.0 1 1.0.0 1
check "same protocol (app)" 0 "$c" app 1.0.0 1 1.2.0 1
check "protocol mismatch" 1 "$c" agent 1.2.0 2 1.0.0 1
check "protocol mismatch (app side)" 1 "$c" app 1.0.0 1 1.2.0 2
check "blocked beats same protocol" 1 "$c" agent 1.1.0 1 1.0.0 1
check "blocked pair seen from app" 1 "$c" app 1.0.0 1 1.1.0 1
check "known_good beats mismatch" 0 "$c" agent 2.0.0 2 1.0.0 1
check "agent without protocol" 0 "$c" agent 1.2.0 none 1.0.0 1
check "app without protocol" 0 "$c" app 1.0.0 none 1.2.0 1
check "empty compatibility file" 0 "$tmp/empty.json" agent 1.2.0 1 1.0.0 1
check "malformed compatibility file" 1 "$tmp/broken.json" agent 1.2.0 1 1.0.0 1
check "malformed file, other not deployed" 1 "$tmp/broken.json" agent 1.2.0 1 "" ""
check "wrong-shaped compatibility file" 1 "$tmp/wrong-shape.json" agent 1.1.0 1 1.0.0 1
check "missing compatibility file" 1 "$tmp/nope.json" agent 1.2.0 1 1.0.0 1
check "unknown component" 2 "$c" display 1.0.0 1 1.0.0 1
check "wrong arg count" 2 "$c" agent 1.0.0

echo "$pass passed, $fail failed"
[[ "$fail" == 0 ]]
