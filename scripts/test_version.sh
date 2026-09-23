#!/usr/bin/env bash
# Tests for scripts/version.sh, run against throwaway git repos.
# Usage: scripts/test_version.sh   (exits non-zero on any failure)
set -euo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/version.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0
fail=0

check() { # check <name> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    pass=$((pass + 1))
    echo "ok   - $1"
  else
    fail=$((fail + 1))
    echo "FAIL - $1: expected '$2', got '$3'"
  fi
}

# Isolate from the user's global/system git config (signing, hooks, etc.).
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
# Don't inherit repo context when run from a git hook.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE

repo="$tmp/repo"
git init -q "$repo"
cd "$repo"
git config user.name test
git config user.email test@example.com
git config commit.gpgsign false
git config tag.gpgsign false

n=0
commit() {
  n=$((n + 1))
  echo "$n" >file
  git add file
  git commit -q -m "c$n"
}
short() { git rev-parse --short HEAD; }
field() { "$script" "$1" | sed -n "s/^$2=//p"; }

# --- no tag yet -------------------------------------------------------------
commit
commit
s="$(short)"
check "untagged clean CANONICAL" "0.0.0+2.g$s" "$(field agent CANONICAL)"
check "untagged clean DOCKER_TAG" "0.0.0-2-g$s" "$(field agent DOCKER_TAG)"
check "REVISION is full sha" "$(git rev-parse HEAD)" "$(field agent REVISION)"
check "REVISION is 40 hex chars" "yes" "$([[ "$(field agent REVISION)" =~ ^[0-9a-f]{40}$ ]] && echo yes || echo no)"
check "output is exactly 3 lines" "3" "$("$script" agent | wc -l | tr -d ' ')"

echo dirty >file
check "untagged dirty CANONICAL" "0.0.0+2.g$s.dirty" "$(field agent CANONICAL)"
check "untagged dirty DOCKER_TAG" "0.0.0-2-g$s-dirty" "$(field agent DOCKER_TAG)"
git checkout -q -- file

# --- clean release tag --------------------------------------------------------
git tag agent-v1.2.3
check "release CANONICAL" "1.2.3" "$(field agent CANONICAL)"
check "release DOCKER_TAG" "1.2.3" "$(field agent DOCKER_TAG)"
check "app ignores agent tag" "0.0.0+2.g$s" "$(field app CANONICAL)"

# --- dirty on tag -------------------------------------------------------------
echo dirty >file
check "dirty on tag CANONICAL" "1.2.3+0.g$s.dirty" "$(field agent CANONICAL)"
check "dirty on tag DOCKER_TAG" "1.2.3-0-g$s-dirty" "$(field agent DOCKER_TAG)"
git checkout -q -- file

# --- ahead of tag ---------------------------------------------------------------
commit
commit
commit
s="$(short)"
check "ahead CANONICAL" "1.2.3+3.g$s" "$(field agent CANONICAL)"
check "ahead DOCKER_TAG" "1.2.3-3-g$s" "$(field agent DOCKER_TAG)"

echo dirty >file
check "dirty ahead CANONICAL" "1.2.3+3.g$s.dirty" "$(field agent CANONICAL)"
check "dirty ahead DOCKER_TAG" "1.2.3-3-g$s-dirty" "$(field agent DOCKER_TAG)"
git checkout -q -- file

# --- the other component's newer tag is ignored ---------------------------------
git tag app-v9.9.9
check "agent ignores newer app tag" "1.2.3+3.g$s" "$(field agent CANONICAL)"
check "app uses its own tag" "9.9.9" "$(field app CANONICAL)"

# --- latest tag chosen when several exist ----------------------------------------
git tag agent-v1.3.0
commit
s="$(short)"
check "latest agent tag chosen" "1.3.0+1.g$s" "$(field agent CANONICAL)"
check "latest app tag chosen" "9.9.9-1-g$s" "$(field app DOCKER_TAG)"

# --- invalid arguments -----------------------------------------------------------
for args in "" "frontend" "agent app" "agent-v"; do
  rc=0
  # shellcheck disable=SC2086  # intentional word splitting of test args
  "$script" $args >/dev/null 2>&1 || rc=$?
  check "invalid arg '$args' exits 2" "2" "$rc"
done
check "usage goes to stderr, not stdout" "" "$("$script" bogus 2>/dev/null || true)"

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
