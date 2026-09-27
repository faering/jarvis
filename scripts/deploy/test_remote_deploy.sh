#!/usr/bin/env bash
# Tests for the Pi deploy scripts (jarvis-deploy-agent, remote-{app,state}.sh,
# jarvis-install-app) and their logging (scripts/lib/log.sh) against stubbed
# docker / sudo / apt / dpkg.
# Usage: scripts/deploy/test_remote_deploy.sh   (exits non-zero on any failure)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin"
mkdir -p "$bin"

# docker: one fake "agent" container whose tag/version come from the compose env file.
# A tag listed in $STUB/bad never turns healthy. Every call is logged to $STUB/docker.log.
cat >"$bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${*%%$'\n'*}" >>"$STUB/docker.log" # first line only (exec's script)
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
      grep -qxF "$tag" "$STUB/bad" 2>/dev/null && echo unhealthy || echo healthy
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
# sudo: only `sudo -n` and only the two sudoers-allowed root scripts; SUDO_FAIL=1 = no sudoers.
cat >"$bin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == -n && -z "${SUDO_FAIL:-}" ]] || exit 1
case "$2" in
  /usr/local/sbin/jarvis-deploy-agent) exec bash "$HERE/jarvis-deploy-agent" "${@:3}" ;;
  /usr/local/sbin/jarvis-install-app)
    deb="${!#}"
    grep -q '^FAIL=1' "$deb" && exit 1
    sed -n 's/^Version=//p' "$deb" >"$STUB/installed"
    ;;
  *) exit 1 ;;
esac
EOF
cat >"$bin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
[[ -s "$STUB/installed" ]] && echo "install ok installed $(cat "$STUB/installed")"
EOF
chmod +x "$bin"/*
export PATH="$bin:$PATH" AGENT_HEALTH_TIMEOUT=5 HERE="$here"
# The shared logger, installed like the Pi setup does (not group/world-writable).
install -d -m 755 "$tmp/lib"
install -m 644 "$here/../lib/log.sh" "$tmp/lib/log.sh"
export JARVIS_LOG_LIB="$tmp/lib/log.sh"

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
fresh() { # fresh pi dirs + stub state: ~deploy/jarvis, /opt/jarvis, /var/lib/jarvis
  local root="$tmp/pi/$1"
  export JARVIS_DIR="$root/home/jarvis" STUB="$tmp/stub/$1" \
    JARVIS_OPT_DIR="$root/opt/jarvis" JARVIS_STATE_DIR="$root/var/lib/jarvis"
  mkdir -p "$JARVIS_DIR/incoming" "$STUB" "$JARVIS_OPT_DIR"
  chmod 755 "$JARVIS_OPT_DIR"
  install -m 644 /dev/null "$JARVIS_OPT_DIR/docker-compose.yml"
  export JARVIS_LOG_DIR="$root/var/log/jarvis"
  install -d -m 2775 "$JARVIS_LOG_DIR"
}
logfile() { echo "$JARVIS_LOG_DIR/jarvis-deploy-$(date -u +%F).log"; }
logged() { grep -qF -- "$1" "$(logfile)" 2>/dev/null; } # logged <text>
# As deploy.yml runs it: ssh pi sudo -n /usr/local/sbin/jarvis-deploy-agent deploy ...
agent() { sudo -n /usr/local/sbin/jarvis-deploy-agent deploy "$1" "$2" 0 >/dev/null 2>&1; }
app() { bash "$here/remote-app.sh" "$1" "$2" 0 >/dev/null 2>&1; }
deb() { # deb <path> <version> [fail]
  printf 'Package=jarvis\nVersion=%s\nFAIL=%s\n' "$2" "${3:-0}" >"$1"
}
not() { ! "$@"; }
has() { grep -q "^$2=$3\$" "$1" 2>/dev/null; }
pulled() { grep -q ' pull ' "$STUB/docker.log" 2>/dev/null; }

# --- agent (jarvis-deploy-agent, via the sudo stub) ---
fresh agent-first-ok
ok "agent: first deploy succeeds" agent 1.0.0 1.0.0
ok "agent: first deploy records state" has "$JARVIS_STATE_DIR/agent.env" AGENT_IMAGE_TAG 1.0.0
ok "agent: runs only the root-owned compose file" \
  grep -q -- "-f $JARVIS_OPT_DIR/docker-compose.yml --env-file $JARVIS_STATE_DIR/" "$STUB/docker.log"
ok "agent: every compose call uses it" \
  not grep -v -e "-f $JARVIS_OPT_DIR/docker-compose.yml" -e '^network ' -e '^inspect ' -e '^exec ' "$STUB/docker.log"
ok "agent: nothing under the deploy user's home reaches docker" not grep -q "$JARVIS_DIR" "$STUB/docker.log"
ok "agent: upgrade succeeds" agent 1.1.0 1.1.0
ok "agent: upgrade records the previous tag" has "$JARVIS_STATE_DIR/agent.env" PREVIOUS_IMAGE_TAG 1.0.0
ok "agent: dev build tag matching its version" agent 1.2.0-3-gabc1234-dirty 1.2.0+3.gabc1234.dirty

fresh agent-first-bad
echo 1.0.0 >"$STUB/bad"
ok "agent: failed first deploy exits non-zero" not agent 1.0.0 1.0.0
ok "agent: failed first deploy leaves no agent running" test ! -e "$STUB/running.env"
ok "agent: failed first deploy writes no state" test ! -e "$JARVIS_STATE_DIR/agent.env"

fresh agent-rollback
agent 1.0.0 1.0.0
echo 2.0.0 >"$STUB/bad"
ok "agent: failed upgrade exits non-zero" not agent 2.0.0 2.0.0
ok "agent: failed upgrade rolls back" has "$STUB/running.env" AGENT_IMAGE_TAG 1.0.0
ok "agent: failed upgrade keeps state" has "$JARVIS_STATE_DIR/agent.env" AGENT_IMAGE_TAG 1.0.0

fresh agent-validate
for t in x/y a:b ../ ../../etc '' '1.0.0 x' 1.0.0:latest ghcr.io/evil/x:1.0.0 1.0.0/../x \
  latest -1.0.0 1.0 $'1.0.0\nx' '1.0.0;id' 1.0.0-dirty; do
  ok "agent: refuses tag '${t//$'\n'/\\n}'" not agent "$t" 1.0.0
done
ok "agent: refuses a tag that isn't its version's" not agent 1.0.1 1.0.0
ok "agent: refuses a malformed version" not agent 1.0.0 '1.0.0 x'
ok "agent: refuses a malformed protocol" \
  not sudo -n /usr/local/sbin/jarvis-deploy-agent deploy 1.0.0 1.0.0 '1;x' 2>/dev/null
ok "agent: refuses extra arguments" \
  not sudo -n /usr/local/sbin/jarvis-deploy-agent deploy 1.0.0 1.0.0 0 x 2>/dev/null
ok "agent: refuses an unknown subcommand" not sudo -n /usr/local/sbin/jarvis-deploy-agent rollback 2>/dev/null
ok "agent: refused tags never reach docker" not pulled
chmod g+w "$JARVIS_OPT_DIR/docker-compose.yml"
ok "agent: refuses a group-writable compose file" not agent 1.0.0 1.0.0
chmod g-w "$JARVIS_OPT_DIR/docker-compose.yml" && chmod o+w "$JARVIS_OPT_DIR"
ok "agent: refuses a world-writable /opt/jarvis" not agent 1.0.0 1.0.0
chmod o-w "$JARVIS_OPT_DIR" && mv "$JARVIS_OPT_DIR/docker-compose.yml" "$tmp/elsewhere.yml"
ln -s "$tmp/elsewhere.yml" "$JARVIS_OPT_DIR/docker-compose.yml"
ok "agent: refuses a symlinked compose file" not agent 1.0.0 1.0.0
rm "$JARVIS_OPT_DIR/docker-compose.yml"
ok "agent: refuses a missing compose file" not agent 1.0.0 1.0.0
ok "agent: never pulled from an untrusted setup" not pulled
install -m 644 /dev/null "$JARVIS_OPT_DIR/docker-compose.yml"
mkdir -p "$JARVIS_STATE_DIR"
exec 8>"$JARVIS_STATE_DIR/deploy.lock"
flock 8
ok "agent: refuses to run next to another deploy" not agent 1.0.0 1.0.0
exec 8>&-
ok "agent: deploys once the lock is free" agent 1.0.0 1.0.0

# --- deploy state (the compat gate reads it) ---
fresh state
ok "state: empty before the first deploy" test -z "$(sudo -n /usr/local/sbin/jarvis-deploy-agent state)"
ok "remote-state: agent empty before the first deploy" test -z "$(bash "$here/remote-state.sh" agent)"
agent 1.0.0 1.0.0
ok "state: prints the deployed tag" grep -qx AGENT_IMAGE_TAG=1.0.0 \
  <(sudo -n /usr/local/sbin/jarvis-deploy-agent state)
ok "remote-state: agent prints only VERSION + PROTOCOL" \
  test "$(bash "$here/remote-state.sh" agent)" == $'VERSION=1.0.0\nPROTOCOL=0'
ok "remote-state: fails when sudo isn't set up" not env SUDO_FAIL=1 bash "$here/remote-state.sh" agent
ok "remote-state: app empty before the first deploy" test -z "$(bash "$here/remote-state.sh" app)"

# --- deploy.yml no longer ships a compose file or runs docker as the deploy user ---
wf="$here/../../.github/workflows/deploy.yml"
ok "deploy.yml: no compose file upload" not grep -q 'docker-compose' "$wf"
ok "deploy.yml: agent rollout goes through the root script" \
  grep -q 'sudo -n /usr/local/sbin/jarvis-deploy-agent deploy' "$wf"

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

# --- the root installer (jarvis-install-app), run unprivileged with its test hooks ---
home="$tmp/installer-home"
mkdir -p "$home/jarvis/incoming" "$home/jarvis/app" "$home/elsewhere"
printf '#!/usr/bin/env bash\necho "$@" >"%s/apt-args"\n' "$tmp" >"$bin/fake-apt"
chmod +x "$bin/fake-apt"
installer() { JARVIS_INSTALL_HOME="$home" APT_GET=fake-apt bash "$here/jarvis-install-app" "$@" >/dev/null 2>&1; }
deb "$home/jarvis/incoming/good.deb" 1.0.0
ok "installer installs a jarvis .deb from incoming/" installer "$home/jarvis/incoming/good.deb"
ok "installer passes only the private copy to apt-get" grep -q 'install -y --allow-downgrades .*/jarvis.deb$' "$tmp/apt-args"
deb "$home/jarvis/app/previous.deb" 0.9.0
ok "installer installs a kept .deb from app/ (rollback)" installer "$home/jarvis/app/previous.deb"
deb "$home/elsewhere/x.deb" 1.0.0
ok "installer refuses a .deb outside ~/jarvis" not installer "$home/elsewhere/x.deb"
ln -s "$home/elsewhere/x.deb" "$home/jarvis/incoming/link.deb"
ok "installer refuses a symlink pointing outside" not installer "$home/jarvis/incoming/link.deb"
printf 'Package=evil\nVersion=1\n' >"$home/jarvis/incoming/evil.deb"
ok "installer refuses another package name" not installer "$home/jarvis/incoming/evil.deb"
ok "installer refuses extra arguments" not installer "$home/jarvis/incoming/good.deb" -o x
ok "installer refuses '..' in the path" not installer "$home/jarvis/incoming/../../elsewhere/x.deb"
mkdir -p "$home/jarvis/incoming/sub" && deb "$home/jarvis/incoming/sub/n.deb" 1.0.0
ok "installer refuses a nested path" not installer "$home/jarvis/incoming/sub/n.deb"
mkdir -p "$home/jarvis/incoming/dir.deb"
ok "installer refuses a directory" not installer "$home/jarvis/incoming/dir.deb"
# A directory swapped for a symlink (e.g. mid-deploy) must not redirect the copy.
deb "$home/elsewhere/good.deb" 1.0.0
mv "$home/jarvis/app" "$home/jarvis/app.real" && ln -s "$home/elsewhere" "$home/jarvis/app"
ok "installer refuses a symlinked directory" not installer "$home/jarvis/app/good.deb"
rm "$home/jarvis/app" && mv "$home/jarvis/app.real" "$home/jarvis/app"

# --- logging (docs/logging.md) ---
fresh log-agent
agent 1.0.0 1.0.0
ok "log: agent deploy writes the deploy component's daily file" test -f "$(logfile)"
ok "log: file is 0640" test "$(stat -c %a "$(logfile)")" == 640
ok "log: spec line with attributes" \
  logged "[INFO ] [deploy] [deploy.agent] [--------] deployed  version=1.0.0 tag=1.0.0"
echo 2.0.0 >"$STUB/bad"
agent 2.0.0 2.0.0 || true
ok "log: rollback logged under its own logger" \
  logged "[WARN ] [deploy] [rollback] [--------] deploy failed, rolling back  version=2.0.0 to=1.0.0"
ok "log: failed health check is an ERROR" logged "[ERROR] [deploy] [deploy.agent] [--------] container is unhealthy"
ok "log: every line is a record jarvis-logs reads" \
  test "$(python3 "$here/../logs/jarvis-logs" --dir "$JARVIS_LOG_DIR" | wc -l)" == "$(wc -l <"$(logfile)")"
ok "log: jarvis-logs finds the rollback at WARN" \
  grep -q '\[rollback\]' <(python3 "$here/../logs/jarvis-logs" --dir "$JARVIS_LOG_DIR" --level WARN)
ok "log: lines also go to stderr" \
  grep -q '\[ERROR\] \[deploy\] \[deploy.agent\]' <(sudo -n /usr/local/sbin/jarvis-deploy-agent deploy x 1.0.0 0 2>&1)
ok "log: stdout of 'state' stays clean" \
  test "$(sudo -n /usr/local/sbin/jarvis-deploy-agent state 2>/dev/null | grep -cv '^[A-Z_]*=')" == 0

fresh log-nodir
rmdir "$JARVIS_LOG_DIR"
ok "log: a missing log folder never fails a deploy" agent 1.0.0 1.0.0
ok "log: ...and creates nothing" test ! -e "$JARVIS_LOG_DIR"

fresh log-symlink
echo keep >"$tmp/victim"
ln -s "$tmp/victim" "$(logfile)"
ok "log: deploy succeeds next to a symlinked log file" agent 1.0.0 1.0.0
ok "log: never writes through a symlink" test "$(cat "$tmp/victim")" == keep
rm "$(logfile)" && mkfifo "$(logfile)"
ok "log: never blocks on a FIFO" timeout 20 bash -c 'sudo -n /usr/local/sbin/jarvis-deploy-agent deploy 1.1.0 1.1.0 0 >/dev/null 2>&1'

fresh log-untrusted
chmod g+w "$JARVIS_LOG_LIB"
out="$(sudo -n /usr/local/sbin/jarvis-deploy-agent deploy 1.0.0 1.0.0 0 2>&1)" && rc=0 || rc=$?
chmod g-w "$JARVIS_LOG_LIB"
ok "log: a group-writable logger is not sourced (deploy still succeeds)" test "$rc" == 0
ok "log: ...it says so on stderr" grep -q "shared logger missing or untrusted" <<<"$out"
ok "log: ...and nothing reaches the file" test ! -e "$(logfile)"

fresh log-installer
deb "$JARVIS_DIR/incoming/ok.deb" 3.0.0
JARVIS_INSTALL_HOME="${JARVIS_DIR%/jarvis}" APT_GET=fake-apt bash "$here/jarvis-install-app" \
  "$JARVIS_DIR/incoming/ok.deb" >/dev/null 2>&1 || true
ok "log: installer logs install.app" \
  logged "[INFO ] [deploy] [install.app] [--------] installed  package=jarvis version=3.0.0"
JARVIS_INSTALL_HOME="${JARVIS_DIR%/jarvis}" APT_GET=fake-apt bash "$here/jarvis-install-app" \
  "/etc/evil path.deb" >/dev/null 2>&1 || true
ok "log: installer refusals are ERRORs, values quoted" \
  logged '[ERROR] [deploy] [install.app] [--------] refusing a .deb outside'
ok "log: ...with the path quoted" logged 'path="/etc/evil path.deb"'
deb "$JARVIS_DIR/incoming/a.deb" 1.0.0
ok "log: remote-app logs deploy.app to stderr" \
  grep -qF '[INFO ] [deploy] [deploy.app] [--------] deploy started' \
  <(bash "$here/remote-app.sh" "$JARVIS_DIR/incoming/a.deb" 1.0.0 0 2>&1)

echo "$pass passed, $fail failed"
((fail == 0))
