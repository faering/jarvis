#!/usr/bin/env bash
# Tests for scripts/deploy/remote-{agent,app}.sh against stubbed docker / apt / dpkg.
# Usage: scripts/deploy/test_remote_deploy.sh   (exits non-zero on any failure)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin"
mkdir -p "$bin"

# docker: one fake "agent" container whose tag/version come from the compose env file.
# A tag starting with "bad" never turns healthy.
cat >"$bin/docker" <<'EOF'
#!/usr/bin/env bash
run="$STUB/running.env"
case "$1" in
  network) exit 0 ;;
  compose)
    while [[ "$1" != --env-file ]]; do shift; done
    env="$2"
    shift 2
    case "$1" in
      pull) exit 0 ;;
      up) cp "$env" "$run" ;;
      ps) [[ -f "$run" ]] && echo cid ;;
      rm) rm -f "$run" ;;
    esac
    ;;
  inspect)
    tag="$(sed -n 's/^AGENT_IMAGE_TAG=//p' "$run")"
    if [[ "$3" == *Health* ]]; then
      [[ "$tag" == bad* ]] && echo unhealthy || echo healthy
    else
      sed -n 's/^VERSION=//p' "$run"
    fi
    ;;
  exec) exit 0 ;; # /version -> 404 (not served yet)
esac
EOF
# A fake .deb is a text file of Package=/Version=/FAIL= lines; FAIL=1 breaks its install.
cat >"$bin/dpkg-deb" <<'EOF'
#!/usr/bin/env bash
sed -n "s/^$3=//p" "$2"
EOF
cat >"$bin/sudo" <<'EOF'
#!/usr/bin/env bash
deb="${!#}"
grep -q '^FAIL=1' "$deb" && exit 1
sed -n 's/^Version=//p' "$deb" >"$STUB/installed"
EOF
cat >"$bin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
[[ -s "$STUB/installed" ]] && echo "install ok installed $(cat "$STUB/installed")"
EOF
chmod +x "$bin"/*
export PATH="$bin:$PATH" AGENT_HEALTH_TIMEOUT=5

pass=0
fail=0
ok() { # ok <name> <condition...>
  local name="$1"
  shift
  if "$@"; then
    pass=$((pass + 1))
    echo "ok   - $name"
  else
    fail=$((fail + 1))
    echo "FAIL - $name"
  fi
}
fresh() { # fresh pi dir + stub state
  export JARVIS_DIR="$tmp/pi/$1" STUB="$tmp/stub/$1"
  mkdir -p "$JARVIS_DIR/incoming" "$STUB"
  touch "$JARVIS_DIR/docker-compose.yml"
}
agent() { bash "$here/remote-agent.sh" "$1" "$2" 0 >/dev/null 2>&1; }
app() { bash "$here/remote-app.sh" "$1" "$2" 0 >/dev/null 2>&1; }
deb() { # deb <path> <version> [fail]
  printf 'Package=jarvis\nVersion=%s\nFAIL=%s\n' "$2" "${3:-0}" >"$1"
}
not() { ! "$@"; }
has() { grep -q "^$2=$3\$" "$1" 2>/dev/null; }

# --- agent ---
fresh agent-first-ok
ok "agent: first deploy succeeds" agent t1 1.0.0
ok "agent: first deploy records state" has "$JARVIS_DIR/state/agent.env" AGENT_IMAGE_TAG t1

fresh agent-first-bad
ok "agent: failed first deploy exits non-zero" not agent bad1 1.0.0
ok "agent: failed first deploy leaves no agent running" test ! -e "$STUB/running.env"
ok "agent: failed first deploy writes no state" test ! -e "$JARVIS_DIR/state/agent.env"

fresh agent-rollback
agent t1 1.0.0
ok "agent: failed upgrade exits non-zero" not agent bad2 2.0.0
ok "agent: failed upgrade rolls back" has "$STUB/running.env" AGENT_IMAGE_TAG t1
ok "agent: failed upgrade keeps state" has "$JARVIS_DIR/state/agent.env" AGENT_IMAGE_TAG t1

# --- app ---
fresh app
deb "$JARVIS_DIR/incoming/1-a.deb" 1.0.0
ok "app: first install succeeds" app "$JARVIS_DIR/incoming/1-a.deb" 1.0.0
ok "app: candidate promoted to current.deb" has "$JARVIS_DIR/app/current.deb" Version 1.0.0
ok "app: staged candidate removed" test ! -e "$JARVIS_DIR/incoming/1-a.deb"

deb "$JARVIS_DIR/incoming/2-a.deb" 1.0.0 1 # same version, broken build
ok "app: failed same-version redeploy exits non-zero" not app "$JARVIS_DIR/incoming/2-a.deb" 1.0.0
ok "app: rollback target survives same-version redeploy" has "$JARVIS_DIR/app/current.deb" FAIL 0
ok "app: rolled back to the previous install" grep -qx 1.0.0 "$STUB/installed"

deb "$JARVIS_DIR/incoming/3-a.deb" 2.0.0
ok "app: upgrade succeeds" app "$JARVIS_DIR/incoming/3-a.deb" 2.0.0
ok "app: upgrade keeps current + previous" \
  has "$JARVIS_DIR/app/current.deb" Version 2.0.0
ok "app: previous.deb is the old current" has "$JARVIS_DIR/app/previous.deb" Version 1.0.0
ok "app: state points at current/previous" has "$JARVIS_DIR/state/app.env" PREVIOUS_DEB "$JARVIS_DIR/app/previous.deb"

ok "app: refuses to install from the kept rollback .deb" not app "$JARVIS_DIR/app/current.deb" 2.0.0
ok "app: refused install leaves current.deb in place" test -f "$JARVIS_DIR/app/current.deb"

echo "$pass passed, $fail failed"
((fail == 0))
