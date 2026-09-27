#!/usr/bin/env bash
# Tests for scripts/pi/setup.sh: runs it in a fake root (JARVIS_ROOT) with apt, systemd,
# users, sshd, nft and tailscale stubbed, then checks the written files and idempotence.
# No root needed. Usage: scripts/pi/test_setup.sh   (exits non-zero on any failure)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$(cd "$here/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin"
mkdir -p "$bin"

# ---- stubs (state lives in $STUB) ----------------------------------------------------------
stub() { cat >"$bin/$1" && chmod +x "$bin/$1"; }
stub dpkg-query <<'EOF'
#!/usr/bin/env bash
grep -qx "${!#}" "$STUB/installed" 2>/dev/null && echo "install ok installed"
EOF
stub apt-get <<'EOF'
#!/usr/bin/env bash
[[ "$1" == update ]] && exit 0
shift 2 # install -y
for p; do
  echo "$p" >>"$STUB/installed"
  case "$p" in
    docker-ce) echo disabled >"$STUB/units/docker.service"; echo "docker:x:990:" >>"$STUB/group" ;;
    tailscale) echo disabled >"$STUB/units/tailscaled.service" ;;
    nftables) echo disabled >"$STUB/units/nftables.service" ;;
  esac
done
EOF
stub dpkg <<'EOF'
#!/usr/bin/env bash
echo arm64
EOF
stub curl <<'EOF'
#!/usr/bin/env bash
while [[ "$1" != -o ]]; do shift; done
[[ -f "$STUB/bogus_key" ]] && echo bogus >"$2" || echo "fake key" >"$2"
EOF
stub gpg <<'EOF'
#!/usr/bin/env bash
[[ -s "${!#}" ]] || exit 2
grep -q bogus "${!#}" && { echo "fpr:::::::::0000:"; exit 0; }
printf 'fpr:::::::::%s:\n' 9DC858229FC7DD38854AE2D88D81803C0EBFCD88 2596A99EAAB33821893C0A79458CA832957F5868
EOF
stub systemctl <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$STUB/calls"
case "$1" in
  is-enabled) [[ -f "$STUB/units/$2" ]] && cat "$STUB/units/$2" || exit 4 ;;
  is-active) exit 3 ;; # nothing running, so nothing gets reloaded
  enable) echo enabled >"$STUB/units/${!#}" ;;
  disable) echo disabled >"$STUB/units/${!#}" ;;
esac
exit 0
EOF
stub getent <<'EOF'
#!/usr/bin/env bash
grep "^$2:" "$STUB/$1" 2>/dev/null
EOF
stub useradd <<'EOF'
#!/usr/bin/env bash
u="${!#}"
echo "$u:x:1001:1001::/home/$u:/bin/bash" >>"$STUB/passwd"
echo "$u" >"$STUB/groups.$u"
mkdir -p "$JARVIS_ROOT/home/$u"
EOF
stub id <<'EOF'
#!/usr/bin/env bash
cat "$STUB/groups.$2" 2>/dev/null
EOF
stub usermod <<'EOF'
#!/usr/bin/env bash
u="${!#}"
echo "$(cat "$STUB/groups.$u") $2" >"$STUB/groups.$u"
EOF
stub groupadd <<'EOF'
#!/usr/bin/env bash
echo "groupadd $*" >>"$STUB/calls"
echo "${!#}:x:$2:" >>"$STUB/group"
EOF
stub gpasswd <<'EOF'
#!/usr/bin/env bash
tr ' ' '\n' <"$STUB/groups.$2" | grep -vx "$3" | paste -sd' ' >"$STUB/groups.$2.new"
mv "$STUB/groups.$2.new" "$STUB/groups.$2"
EOF
stub visudo <<'EOF'
#!/usr/bin/env bash
grep -q NOPASSWD "${!#}"
EOF
stub ssh-keygen <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
# sshd -T: the drop-in's keywords, lowercased; the Match block only with -C user=deploy.
stub sshd <<'EOF'
#!/usr/bin/env bash
conf="$JARVIS_ROOT/etc/ssh/sshd_config.d/10-jarvis.conf"
case "$1" in
  -t) grep -q '^Match ' "$conf" ;;
  -T) [[ "${3:-}" == user=deploy* ]] && body="$(cat "$conf")" || body="$(sed '/^Match /,$d' "$conf")"
      sed -n 's/^ *\([A-Za-z]\+\) \(.*\)/\L\1\E \2/p' <<<"$body" ;;
esac
EOF
stub nft <<'EOF'
#!/usr/bin/env bash
echo "nft $*" >>"$STUB/calls"
EOF
stub tailscale <<'EOF'
#!/usr/bin/env bash
[[ -f "$STUB/ts_down" ]] && echo '{"BackendState":"NeedsLogin"}' || echo '{"BackendState":"Running"}'
EOF

# ---- fixture: a copy of the repo files setup.sh reads, and a fresh Pi ----------------------
new_pi() { # new_pi <name>: sets R, S, REPO
  local d="$tmp/$1"
  R="$d/root" S="$d/stub" REPO="$d/repo"
  mkdir -p "$R/etc" "$R/home/pi/.ssh" "$R/root" "$S/units" "$REPO/scripts/pi" "$REPO/scripts/deploy" "$REPO/deploy/pi" \
    "$REPO/scripts/lib" "$REPO/scripts/logs"
  cp "$here/setup.sh" "$REPO/scripts/pi/"
  cp "$src/scripts/lib/log.sh" "$REPO/scripts/lib/"
  cp "$src/scripts/logs/jarvis-logs" "$REPO/scripts/logs/"
  cp "$src/scripts/deploy/jarvis-install-app" "$REPO/scripts/deploy/"
  cp "$src/deploy/pi/docker-compose.yml" "$REPO/deploy/pi/"
  echo 'VERSION_CODENAME=trixie' >"$R/etc/os-release"
  echo "ssh-ed25519 AAAAC3op pi@pc" >"$R/home/pi/.ssh/authorized_keys"
  printf 'HISTCONTROL=ignoreboth\nshopt -s histappend\nHISTSIZE=1000\nHISTFILESIZE=2000\n' >"$R/home/pi/.bashrc"
  echo 'PS1=x' >"$R/root/.bashrc"
  echo "ssh-ed25519 AAAAC3deploy github-deploy" >"$d/deploy.pub"
  printf 'root:x:0:0::/root:/bin/bash\npi:x:1000:1000::/home/pi:/bin/bash\n' >"$S/passwd"
  echo pi >"$S/groups.pi"
  : >"$S/group"
  for u in ssh.service avahi-daemon.service avahi-daemon.socket bluetooth.service apt-daily.timer apt-daily-upgrade.timer; do
    echo enabled >"$S/units/$u"
  done
}
run() { # run <setup args...>; output in $out, exit code in $rc
  rc=0
  out="$(JARVIS_ROOT="$R" STUB="$S" PATH="$bin:$PATH" bash "$REPO/scripts/pi/setup.sh" --operator pi "$@" </dev/null 2>&1)" || rc=$?
}
snapshot() { (cd "$R" && find . -printf '%p %m\n' -type f -exec md5sum {} + | sort); }

pass=0 fail=0
ok() {
  pass=$((pass + 1))
  echo "  ok: $1"
}
bad() {
  fail=$((fail + 1))
  echo "  FAIL: $1"
  while IFS= read -r line; do printf '      | %s\n' "$line"; done <<<"$out"
}
check() { # check <desc> <cmd...>
  local desc="$1"
  shift
  if "$@"; then ok "$desc"; else bad "$desc"; fi
}
has() { grep -qxF -- "$2" "$R$1"; } # has <path> <exact line>
mode() { [[ "$(stat -c %a "$R$1")" == "$2" ]]; }

# ---- fresh Pi ------------------------------------------------------------------------------
echo "fresh Pi, full run"
new_pi fresh
echo '{"data-root": "/srv/docker", "log-driver": "json-file", "log-opts": {"max-size": "10m", "tag": "{{.Name}}"}}' |
  install -D /dev/stdin "$R/etc/docker/daemon.json"
before="$(snapshot)"
run --check
check "--check on a fresh Pi reports drift (exit 1)" test "$rc" -eq 1
check "--check changes nothing" test "$before" == "$(snapshot)"

run --deploy-key "$tmp/fresh/deploy.pub"
check "first run succeeds" test "$rc" -eq 0
f=/etc/ssh/sshd_config.d/10-jarvis.conf
check "sshd: no passwords" has $f "PasswordAuthentication no"
check "sshd: no keyboard-interactive" has $f "KbdInteractiveAuthentication no"
check "sshd: no root login" has $f "PermitRootLogin no"
check "sshd: only operator + deploy" has $f "AllowUsers pi deploy"
check "sshd: deploy key file is root-owned, outside home" has $f "    AuthorizedKeysFile /etc/ssh/authorized_keys/%u"
check "deploy key is restricted" has /etc/ssh/authorized_keys/deploy "restrict ssh-ed25519 AAAAC3deploy github-deploy"
f=/etc/sudoers.d/jarvis-deploy
check "sudoers: exactly the two scripts" has $f \
  "deploy ALL=(root) NOPASSWD: /usr/local/sbin/jarvis-deploy-agent, /usr/local/sbin/jarvis-install-app"
check "sudoers mode 440" mode $f 440
check "installer installed 755" mode /usr/local/sbin/jarvis-install-app 755
check "installer is the repo copy" cmp -s "$src/scripts/deploy/jarvis-install-app" "$R/usr/local/sbin/jarvis-install-app"
check "deploy-agent absent -> notice" grep -q "jarvis-deploy-agent not in this checkout" <<<"$out"
check "compose file in /opt/jarvis (644)" mode /opt/jarvis/docker-compose.yml 644
check "agent.env created empty, 600" bash -c "[[ ! -s '$R/opt/jarvis/agent.env' ]] && [[ \$(stat -c %a '$R/opt/jarvis/agent.env') == 600 ]]"
check "/var/lib/jarvis is 700" mode /var/lib/jarvis 700
for d in jarvis jarvis/incoming jarvis/app jarvis/state; do
  check "~deploy/$d is 750" mode "/home/deploy/$d" 750
done
check "deploy not in docker group" bash -c "! grep -qw docker '$S/groups.deploy'"
check "operator in docker group" grep -qw docker "$S/groups.pi"
f=/etc/nftables.conf
check "nft: default drop" grep -q "policy drop;" "$R$f"
check "nft: SSH only on tailscale0" grep -q 'iifname "tailscale0" tcp dport 22 accept' "$R$f"
check "nft: Tailscale UDP" grep -q "udp dport 41641 accept" "$R$f"
check "nft: loopback" grep -q 'iif "lo" accept' "$R$f"
check "nft: never flushes Docker's rules" bash -c "! grep -q 'flush ruleset' '$R$f'"
check "nft: checked before loaded" bash -c "grep -n '^nft' '$S/calls' | head -1 | grep -q -- '-c -f'"
check "nft: stop only drops our table" has /etc/systemd/system/nftables.service.d/10-jarvis.conf \
  "ExecStop=/usr/sbin/nft delete table inet jarvis"
f=/etc/systemd/journald.conf.d/10-jarvis.conf
check "journald persistent" has $f "Storage=persistent"
check "journald size cap" has $f "SystemMaxUse=500M"
check "journald retention" has $f "MaxRetentionSec=1month"
dj="$R/etc/docker/daemon.json"
check "daemon.json: journald driver" test "$(jq -r '."log-driver"' "$dj")" == journald
check "daemon.json: other keys kept" test "$(jq -r '."data-root"' "$dj")" == /srv/docker
check "daemon.json: journald-compatible log-opts kept" test "$(jq -r '."log-opts".tag' "$dj")" == "{{.Name}}"
check "daemon.json: json-file-only log-opts dropped" test "$(jq -r '."log-opts"."max-size"' "$dj")" == null
f=/etc/apt/apt.conf.d/52jarvis-unattended-upgrades
check "updates: unattended on" has $f 'APT::Periodic::Unattended-Upgrade "1";'
check "updates: reboot policy" has $f 'Unattended-Upgrade::Automatic-Reboot-Time "04:00";'
check "docker repo pinned to trixie" has /etc/apt/sources.list.d/docker.sources "Suites: trixie"
f=/etc/profile.d/jarvis-history.sh
check "history: size" has $f "HISTFILESIZE=100000"
check "history: timestamps" has $f "HISTTIMEFORMAT='%F %T  '"
check "history: ignoredups" has $f "HISTCONTROL=ignoredups"
check "history: file is valid bash" bash -n "$R$f"
check "history: Debian's HISTFILESIZE commented out" bash -c "! grep -q '^HISTFILESIZE=' '$R/home/pi/.bashrc'"
check "history: operator .bashrc sources it" grep -q "jarvis-history.sh; fi # jarvis$" "$R/home/pi/.bashrc"
check "history: root .bashrc sources it" grep -q "jarvis-history.sh; fi # jarvis$" "$R/root/.bashrc"
hist="$(HOME="$R/home/pi" bash -ic "source '$R$f'; echo \$HISTSIZE \$HISTFILESIZE; source '$R$f'; echo \"\$PROMPT_COMMAND\"" 2>/dev/null)"
check "history: applies in an interactive shell, PROMPT_COMMAND added once" \
  test "$hist" == "$(printf '50000 100000\nhistory -a')"
check "log group jarvis-log with fixed GID 2750" grep -qx "jarvis-log:x:2750:" "$S/group"
check "log group created with --gid" grep -q "groupadd --gid 2750 jarvis-log" "$S/calls"
check "/var/log/jarvis is 2775 (setgid)" mode /var/log/jarvis 2775
check "operator (app user) in jarvis-log" grep -qw jarvis-log "$S/groups.pi"
check "deploy user not in jarvis-log" bash -c "! grep -qw jarvis-log '$S/groups.deploy'"
check "app launch env: JARVIS_LOG_DIR" has /etc/environment.d/60-jarvis-logs.conf "JARVIS_LOG_DIR=/var/log/jarvis"
check "logger installed 644" mode /usr/local/lib/jarvis/log.sh 644
check "logger folder 755" mode /usr/local/lib/jarvis 755
check "logger is the repo copy" cmp -s "$src/scripts/lib/log.sh" "$R/usr/local/lib/jarvis/log.sh"
check "jarvis-logs installed 755" mode /usr/local/bin/jarvis-logs 755
check "jarvis-logs is the repo copy" cmp -s "$src/scripts/logs/jarvis-logs" "$R/usr/local/bin/jarvis-logs"
f=/etc/systemd/system/jarvis-logs-prune.service
check "prune service runs jarvis-logs prune" has $f "ExecStart=/usr/local/bin/jarvis-logs prune --dir /var/log/jarvis"
check "prune service: throwaway user" has $f "DynamicUser=yes"
check "prune service: only the log folder is writable" has $f "ReadWritePaths=/var/log/jarvis"
check "prune service: via the log group" has $f "SupplementaryGroups=jarvis-log"
check "prune timer hourly" has /etc/systemd/system/jarvis-logs-prune.timer "OnCalendar=hourly"
check "prune timer enabled" test "$(cat "$S/units/jarvis-logs-prune.timer")" == enabled
check "systemd reloaded before enabling the timer" bash -c \
  "grep -n 'systemctl' '$S/calls' | grep -A99 daemon-reload | grep -q 'enable --now jarvis-logs-prune.timer'"
check "avahi disabled" test "$(cat "$S/units/avahi-daemon.service")" == disabled
check "bluetooth kept" test "$(cat "$S/units/bluetooth.service")" == enabled
check "docker enabled" test "$(cat "$S/units/docker.service")" == enabled

echo "second run is a no-op"
before="$(snapshot)"
run
check "second run succeeds" test "$rc" -eq 0
check "second run: 0 changes" grep -q "applied 0 change(s)" <<<"$out"
check "second run: files untouched" test "$before" == "$(snapshot)"
run --check
check "--check after setup: no drift" test "$rc" -eq 0

echo "drift is reported, then repaired"
echo "PasswordAuthentication yes" >"$R/etc/ssh/sshd_config.d/10-jarvis.conf"
echo "secret=1" >"$R/opt/jarvis/agent.env"
touch "$REPO/scripts/deploy/jarvis-deploy-agent"
run --check
check "--check: edited sshd drop-in is drift" test "$rc" -eq 1
check "--check: names the file" grep -q "DRIFT: /etc/ssh/sshd_config.d/10-jarvis.conf" <<<"$out"
check "--check: left it alone" has /etc/ssh/sshd_config.d/10-jarvis.conf "PasswordAuthentication yes"
run
check "re-run repairs it" has /etc/ssh/sshd_config.d/10-jarvis.conf "PasswordAuthentication no"
check "agent.env is never overwritten" has /opt/jarvis/agent.env "secret=1"
check "deploy-agent installed once present (755)" mode /usr/local/sbin/jarvis-deploy-agent 755

# ---- lockout guards ------------------------------------------------------------------------
echo "no operator key: ssh hardening deferred"
new_pi nokey
rm "$R/home/pi/.ssh/authorized_keys"
run
check "exit 3 (deferred)" test "$rc" -eq 3
check "no sshd drop-in written" test ! -e "$R/etc/ssh/sshd_config.d/10-jarvis.conf"
check "says why" grep -q "no ~/.ssh/authorized_keys" <<<"$out"

echo "Tailscale not up: firewall deferred"
new_pi nots
touch "$S/ts_down"
run
check "exit 3 (deferred)" test "$rc" -eq 3
check "no firewall written" test ! -e "$R/etc/nftables.conf"
check "no firewall loaded" bash -c "! grep -q '^nft' '$S/calls'"

echo "refuses to run as non-root without the test hook"
rc=0
out="$(bash "$REPO/scripts/pi/setup.sh" --operator pi 2>&1)" || rc=$?
check "exit 2" test "$rc" -eq 2

echo "existing deploy user in the docker group"
new_pi olddeploy
echo "deploy:x:1001:1001::/home/deploy:/bin/bash" >>"$S/passwd"
echo "deploy docker" >"$S/groups.deploy"
mkdir -p "$R/home/deploy"
run
check "removed from docker group" bash -c "! grep -qw docker '$S/groups.deploy'"

echo "jarvis-log with the wrong GID aborts"
new_pi badgid
echo "jarvis-log:x:1234:" >"$S/group"
run
check "fails" test "$rc" -eq 1
check "says how to fix it" grep -q "groupmod -g 2750 jarvis-log" <<<"$out"

echo "a download that isn't the pinned key aborts"
new_pi badkey
touch "$S/bogus_key"
run
check "fails" test "$rc" -eq 1
check "no key installed" test ! -e "$R/etc/apt/keyrings/docker.asc"

echo
echo "passed: $pass, failed: $fail"
((fail == 0))
