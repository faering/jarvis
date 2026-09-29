#!/usr/bin/env bash
# Reproducible, hardened setup of the Jarvis Pi (Raspberry Pi OS Trixie, 64-bit). Runs ON THE
# PI from a checkout of this repo, as root:
#
#   sudo scripts/pi/setup.sh [--check] [--operator USER] [--deploy-key FILE]
#
#   --check            report drift only; change nothing (exit 1 if anything differs)
#   --operator USER    your own login (default: $SUDO_USER); keeps sudo, may use docker
#   --deploy-key FILE  public key of the GitHub deploy key, for the `deploy` user
#
# Idempotent: re-run it any time (e.g. after `git pull`) to converge the Pi again.
# Exit: 0 done / no drift, 1 error or drift (--check), 3 applied but some steps deferred.
# Guide: docs/pi-setup.md. Why each step: #131 (hardening), #132 (setup), #126 (log files).
#
# Test hook: JARVIS_ROOT=<dir> prefixes every path read or written, so
# scripts/pi/test_setup.sh can run it without root (commands stubbed on PATH).
# It is refused as root.
set -euo pipefail

# Pinned apt signing keys (primary key fingerprints); a download that doesn't match aborts.
DOCKER_KEY_FPR=9DC858229FC7DD38854AE2D88D81803C0EBFCD88
TAILSCALE_KEY_FPR=2596A99EAAB33821893C0A79458CA832957F5868
# GitHub CLI's apt key (cli.github.com docs, key created 2026-04-07); gh verifies release
# provenance offline (#121).
GH_KEY_FPR=7F38BBB59D064DBCB3D84D725612B36462313325
DEPLOY_USER=deploy
# Log files (docs/logging.md): the agent container joins the group by this fixed number.
LOG_GROUP=jarvis-log
LOG_GID=2750
LOG_DIR=/var/log/jarvis
# Unused on this device: mDNS (Tailscale MagicDNS replaces jarvis.local), printing, modems.
UNUSED_UNITS=(avahi-daemon.service avahi-daemon.socket cups.service cups.socket cups.path
  cups-browsed.service ModemManager.service)
MARK="managed by jarvis scripts/pi/setup.sh; local edits are overwritten"

usage() { sed -n '2,/^set -euo/{/^#/!q;s/^# \{0,1\}//p}' "$0"; }
check=0 operator="${SUDO_USER:-}" deploy_key=""
while (($#)); do
  case "$1" in
    --check) check=1 ;;
    --operator) operator="${2:?--operator needs a user}" && shift ;;
    --deploy-key) deploy_key="${2:?--deploy-key needs a file}" && shift ;;
    -h | --help) usage && exit 0 ;;
    *) usage >&2 && exit 2 ;;
  esac
  shift
done

R="${JARVIS_ROOT:-}"
fake=0
if [[ -n "$R" ]]; then
  [[ $EUID -ne 0 ]] || {
    echo "JARVIS_ROOT is a test hook; refusing it as root" >&2
    exit 2
  }
  fake=1
elif [[ $EUID -ne 0 ]]; then
  echo "run as root: sudo $0 $*" >&2
  exit 2
fi
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
tmpd="$(mktemp -d)"
trap 'rm -rf "$tmpd"' EXIT

# ---- helpers -------------------------------------------------------------------------------
changes=0 drift=0 updated=0
deferred=()
log() { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] WARNING: %s\n' "$*" >&2; }
die() {
  printf '[setup] ERROR: %s\n' "$*" >&2
  exit 1
}
section() { printf '\n== %s ==\n' "$*"; }
p() { printf '%s%s' "$R" "$1"; } # real path -> path under the (test) root
defer() {
  warn "deferred: $*"
  deferred+=("$*")
  ((check)) && drift=$((drift + 1))
  return 0
}

# act <what> <cmd...>: run the command, or in --check mode only report it as drift.
act() {
  local what="$1"
  shift
  if ((check)); then
    log "DRIFT: $what"
    drift=$((drift + 1))
    return 0
  fi
  log "change: $what"
  "$@"
  changes=$((changes + 1))
}

meta_ok() { # meta_ok <path> <mode> <owner:group>
  [[ "$(stat -c %a "$1")" == "$2" ]] || return 1
  ((fake)) || [[ "$(stat -c %U:%G "$1")" == "$3" ]]
}
put() { # put <src> <dst> <mode> <owner:group>
  if ((fake)); then
    install -m "$3" "$1" "$2"
  else
    install -m "$3" -o "${4%%:*}" -g "${4#*:}" "$1" "$2"
  fi
}

# ensure_file <path> <mode> <owner:group> < content. Returns 0 only when it wrote the file.
ensure_file() {
  local dst tmp
  dst="$(p "$1")"
  tmp="$(mktemp -p "$tmpd")"
  cat >"$tmp"
  if [[ -f "$dst" && ! -L "$dst" ]] && cmp -s "$tmp" "$dst" && meta_ok "$dst" "$2" "$3"; then
    return 1
  fi
  if ((check)); then
    log "DRIFT: $1"
    drift=$((drift + 1))
    return 1
  fi
  mkdir -p "$(dirname "$dst")"
  put "$tmp" "$dst" "$2" "$3"
  log "wrote $1"
  changes=$((changes + 1))
}

ensure_dir() { # ensure_dir <path> <mode> <owner:group>
  local dst
  dst="$(p "$1")"
  [[ -d "$dst" && ! -L "$dst" ]] && meta_ok "$dst" "$2" "$3" && return 0
  if ((fake)); then
    act "dir $1 ($2)" install -d -m "$2" "$dst"
  else
    act "dir $1 ($2 $3)" install -d -m "$2" -o "${3%%:*}" -g "${3#*:}" "$dst"
  fi
}

is_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'; }
apt_install() {
  local pkg missing=()
  for pkg; do is_installed "$pkg" || missing+=("$pkg"); done
  ((${#missing[@]})) || return 0
  if ((!check && !updated)); then
    apt-get update
    updated=1
  fi
  act "install ${missing[*]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

unit_state() { systemctl is-enabled "$1" 2>/dev/null || true; }
ensure_enabled() { # ensure_enabled <unit>: enabled and running, if the unit exists
  case "$(unit_state "$1")" in
    enabled | static | alias | indirect | generated) ;;
    "" | not-found) [[ $check -eq 1 ]] || warn "$1 not found" ;;
    *) act "enable $1" systemctl enable --now "$1" ;;
  esac
}
reload_if_active() { # <unit> <reload|restart>
  ((check)) || ! systemctl is-active --quiet "$1" || systemctl "$2" "$1"
}

key_fpr_ok() { # key_fpr_ok <keyfile> <fingerprint>
  local gh
  [[ -s "$1" ]] || return 1
  gh="$(mktemp -d -p "$tmpd")"
  GNUPGHOME="$gh" gpg --batch --show-keys --with-colons "$1" 2>/dev/null |
    awk -F: '$1 == "fpr" { print $10 }' | grep -qx "$2"
}
ensure_key() { # ensure_key <dest> <url> <fingerprint>
  local tmp
  key_fpr_ok "$(p "$1")" "$3" && return 0
  if ((check)); then
    log "DRIFT: $1 (missing, or not key $3)"
    drift=$((drift + 1))
    return 0
  fi
  tmp="$tmpd/key"
  curl -fsSL "$2" -o "$tmp"
  key_fpr_ok "$tmp" "$3" || die "$2 is not key $3; if the vendor rotated it, verify and update the pin in $0"
  ensure_file "$1" 644 root:root <"$tmp" || :
}

in_group() { id -nG "$1" 2>/dev/null | tr ' ' '\n' | grep -qx "$2"; }
home_of() { getent passwd "$1" | cut -d: -f6; }

# ---- preflight -----------------------------------------------------------------------------
[[ -n "$operator" && "$operator" != root && "$operator" != "$DEPLOY_USER" ]] ||
  die "can't tell who you are: run via sudo from your own login, or pass --operator USER"
getent passwd "$operator" >/dev/null || die "operator user '$operator' does not exist"
op_home="$(home_of "$operator")"
# shellcheck disable=SC1090,SC1091
codename="$(. "$(p /etc/os-release)" && echo "${VERSION_CODENAME:-}")"
[[ -n "$codename" ]] || die "no VERSION_CODENAME in /etc/os-release"
arch="$(dpkg --print-architecture)"
((check)) && log "check mode: reporting drift only, changing nothing"
log "operator=$operator codename=$codename arch=$arch repo=$repo"

# ---- 1. packages ---------------------------------------------------------------------------
section "packages"
apt_install ca-certificates curl gpg jq python3 nftables unattended-upgrades vim
# Docker and Tailscale from their official apt repos (arm64 Debian builds), keys pinned above.
ensure_key /etc/apt/keyrings/docker.asc https://download.docker.com/linux/debian/gpg "$DOCKER_KEY_FPR"
ensure_key /usr/share/keyrings/tailscale-archive-keyring.gpg \
  "https://pkgs.tailscale.com/stable/debian/$codename.noarmor.gpg" "$TAILSCALE_KEY_FPR"
if [[ -f "$(p /etc/apt/sources.list.d/docker.list)" ]] &&
  grep -q download.docker.com "$(p /etc/apt/sources.list.d/docker.list)"; then
  act "remove duplicate docker.list (get.docker.com); docker.sources replaces it" \
    rm -f "$(p /etc/apt/sources.list.d/docker.list)"
fi
if ensure_file /etc/apt/sources.list.d/docker.sources 644 root:root <<EOF; then updated=0; fi
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $codename
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
# Same file name and line as Tailscale's own installer, so the two never conflict.
if ensure_file /etc/apt/sources.list.d/tailscale.list 644 root:root <<EOF; then updated=0; fi
deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/debian $codename main
EOF
# GitHub CLI (gh), only to verify release provenance offline (#121); same line as its docs.
ensure_key /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  https://cli.github.com/packages/githubcli-archive-keyring.gpg "$GH_KEY_FPR"
if ensure_file /etc/apt/sources.list.d/github-cli.list 644 root:root <<EOF; then updated=0; fi
deb [arch=$arch signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main
EOF

# ---- 2. logs: journald on disk + Docker's journald driver (before Docker starts) ------------
section "journald + docker logging"
# 99-: drop-ins apply in file-name order across /etc and /usr/lib, and Raspberry Pi OS's
# /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf sets Storage=volatile (#212).
if [[ -e "$(p /etc/systemd/journald.conf.d/10-jarvis.conf)" ]]; then
  act "remove journald 10-jarvis.conf (now 99-jarvis.conf)" rm -f "$(p /etc/systemd/journald.conf.d/10-jarvis.conf)"
fi
if ensure_file /etc/systemd/journald.conf.d/99-jarvis.conf 644 root:root <<EOF; then
# $MARK (#132, #212)
# Keep the journal across reboots; cap it for the SD card. Read: journalctl -b -1, -u docker
[Journal]
Storage=persistent
SystemMaxUse=500M
SystemKeepFree=1G
MaxRetentionSec=1month
EOF
  reload_if_active systemd-journald restart
fi
if ((!fake)) && command -v systemd-analyze >/dev/null; then
  storage="$(systemd-analyze cat-config systemd/journald.conf 2>/dev/null | sed -n 's/^Storage=//p' | tail -n1)"
  if [[ -n "$storage" && "$storage" != persistent ]]; then
    ((check)) && drift=$((drift + 1))
    warn "journald Storage=$storage wins over ours (see: systemd-analyze cat-config systemd/journald.conf)"
  fi
fi
# Merge into daemon.json: set only log-driver (and drop json-file-only log-opts, which
# journald rejects); every other key is kept.
dj="$(p /etc/docker/daemon.json)"
if ! command -v jq >/dev/null; then
  ((check)) && log "DRIFT: /etc/docker/daemon.json (jq not installed yet)" && drift=$((drift + 1))
  ((check)) || die "jq is missing"
else
  if [[ -f "$dj" ]]; then
    jq empty "$dj" 2>/dev/null || die "/etc/docker/daemon.json is not valid JSON; fix it first"
    cur="$(cat "$dj")"
  else
    cur='{}'
  fi
  if ! jq -e '."log-driver" == "journald"' <<<"$cur" >/dev/null; then
    old="$(jq -r '."log-driver" // empty' <<<"$cur")"
    [[ -z "$old" ]] || warn "daemon.json log-driver '$old' -> journald"
    jq '."log-driver" = "journald"
      | if ."log-opts" then ."log-opts" |= del(.["max-size"], .["max-file"], .["compress"]) else . end' \
      <<<"$cur" >"$tmpd/daemon.json"
    if ensure_file /etc/docker/daemon.json 644 root:root <"$tmpd/daemon.json"; then
      # Existing containers keep their old driver until recreated (the next deploy does that).
      reload_if_active docker restart
    fi
  fi
fi

# ---- 3. docker + tailscale -----------------------------------------------------------------
section "docker + tailscale"
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin tailscale gh
ensure_enabled docker.service
ensure_enabled tailscaled.service

# ---- 4. users, dirs, root-owned deploy scripts, sudoers ------------------------------------
section "users + deploy scripts"
if ! getent passwd "$DEPLOY_USER" >/dev/null; then
  # No password is set, so the account is locked for password login; SSH key only.
  act "create user $DEPLOY_USER" useradd --create-home --home-dir "/home/$DEPLOY_USER" \
    --user-group --shell /bin/bash "$DEPLOY_USER"
fi
if getent passwd "$DEPLOY_USER" >/dev/null; then
  # Docker access is root-equivalent: the deploy key must not have it (#131).
  if in_group "$DEPLOY_USER" docker; then
    act "remove $DEPLOY_USER from the docker group" gpasswd -d "$DEPLOY_USER" docker
  fi
  ensure_dir "/home/$DEPLOY_USER" 750 "$DEPLOY_USER:$DEPLOY_USER"
  for d in jarvis jarvis/incoming jarvis/app jarvis/state; do
    ensure_dir "/home/$DEPLOY_USER/$d" 750 "$DEPLOY_USER:$DEPLOY_USER"
  done
fi
# The operator is you at the keyboard: already root via sudo, so docker adds no privilege.
if getent group docker >/dev/null && ! in_group "$operator" docker; then
  act "add $operator to the docker group (log in again to use it)" usermod -aG docker "$operator"
fi

# The deploy key lives outside the deploy user's home (sshd_config drop-in below), so a
# stolen key can't add more keys.
ensure_dir /etc/ssh/authorized_keys 755 root:root
if [[ -n "$deploy_key" ]]; then
  key="$(grep -Ev '^[[:space:]]*(#|$)' "$deploy_key" | head -n1)"
  [[ "$key" =~ ^(ssh-|ecdsa-|sk-) ]] || die "$deploy_key: expected one OpenSSH public key line"
  ssh-keygen -lf "$deploy_key" >/dev/null || die "$deploy_key: not a valid public key"
  # restrict: no port/agent/X11 forwarding, no pty; deploys only run commands and copy files.
  ensure_file "/etc/ssh/authorized_keys/$DEPLOY_USER" 644 root:root <<<"restrict $key" || :
elif [[ ! -s "$(p "/etc/ssh/authorized_keys/$DEPLOY_USER")" ]]; then
  log "note: no deploy key yet; re-run with --deploy-key jarvis-deploy.pub (docs/pi-setup.md)"
fi

ensure_file /usr/local/sbin/jarvis-install-app 755 root:root <"$repo/scripts/deploy/jarvis-install-app" || :
if [[ -f "$repo/scripts/deploy/jarvis-deploy-agent" ]]; then
  ensure_file /usr/local/sbin/jarvis-deploy-agent 755 root:root <"$repo/scripts/deploy/jarvis-deploy-agent" || :
else
  log "note: scripts/deploy/jarvis-deploy-agent not in this checkout yet; skipped (agent deploys need it)"
fi
sudoers="$tmpd/sudoers"
cat >"$sudoers" <<EOF
# $MARK (#131)
# The deploy key may run exactly these two root-owned scripts, nothing else.
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/local/sbin/jarvis-deploy-agent, /usr/local/sbin/jarvis-install-app
EOF
visudo -cf "$sudoers" >/dev/null || die "generated sudoers does not validate"
ensure_file /etc/sudoers.d/jarvis-deploy 440 root:root <"$sudoers" || :

ensure_dir /opt/jarvis 755 root:root
ensure_file /opt/jarvis/docker-compose.yml 644 root:root <"$repo/deploy/pi/docker-compose.yml" || :
if [[ ! -e "$(p /opt/jarvis/agent.env)" ]]; then
  # Runtime config and secrets (keys as in .env.example). Created once, never overwritten.
  ensure_file /opt/jarvis/agent.env 600 root:root </dev/null || :
elif ! meta_ok "$(p /opt/jarvis/agent.env)" 600 root:root; then
  act "fix /opt/jarvis/agent.env permissions (root 600)" \
    bash -c "chmod 600 \"\$1\"; ((\$2)) || chown root:root \"\$1\"" _ "$(p /opt/jarvis/agent.env)" "$fake"
fi
ensure_dir /var/lib/jarvis 700 root:root

# ---- 4b. log files (docs/logging.md, ADR 0011) ---------------------------------------------
section "log files"
gid="$(getent group "$LOG_GROUP" | cut -d: -f3 || true)"
if [[ -z "$gid" ]]; then
  taken="$(getent group "$LOG_GID" | cut -d: -f1 || true)"
  [[ -z "$taken" ]] || die "GID $LOG_GID is taken by group '$taken'; $LOG_GROUP needs it (compose group_add)"
  act "create group $LOG_GROUP (GID $LOG_GID)" groupadd --gid "$LOG_GID" "$LOG_GROUP"
elif [[ "$gid" != "$LOG_GID" ]]; then
  die "group $LOG_GROUP has GID $gid, not $LOG_GID (compose group_add): sudo groupmod -g $LOG_GID $LOG_GROUP, then re-run"
fi
# setgid: every file created inside belongs to the group. Writers: the agent container
# (group_add), the app (the operator runs the display session) and the root deploy scripts.
ensure_dir "$LOG_DIR" 2775 "root:$LOG_GROUP"
if ! in_group "$operator" "$LOG_GROUP"; then
  act "add $operator to $LOG_GROUP (the app writes its log; log in again)" usermod -aG "$LOG_GROUP" "$operator"
fi
# The app reads its log folder from its launch environment (systemd user session).
ensure_file /etc/environment.d/60-jarvis-logs.conf 644 root:root <<EOF || :
# $MARK (#126)
JARVIS_LOG_DIR=$LOG_DIR
EOF
# A Jarvis device boots into Jarvis: the desktop session starts the app full screen at
# login (XDG autostart; TryExec skips it until the first app deploy). #167
ensure_file /etc/xdg/autostart/jarvis.desktop 644 root:root <<EOF || :
# $MARK (#167)
[Desktop Entry]
Type=Application
Name=Jarvis
Comment=Start Jarvis full screen at login
TryExec=/usr/bin/jarvis-app
Exec=/usr/bin/jarvis-app --fullscreen
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
# Root-owned: the root deploy scripts source the logger only if root owns it and its folder.
ensure_dir /usr/local/lib/jarvis 755 root:root
ensure_file /usr/local/lib/jarvis/log.sh 644 root:root <"$repo/scripts/lib/log.sh" || :
ensure_file /usr/local/bin/jarvis-logs 755 root:root <"$repo/scripts/logs/jarvis-logs" || :

# ---- 4c. release provenance (#121) ---------------------------------------------------------
# The root deploy scripts verify every artifact offline against a Sigstore trusted root that
# a daily timer refreshes (no GitHub token on the Pi).
section "release provenance"
ensure_file /usr/local/lib/jarvis/verify.sh 644 root:root <"$repo/scripts/lib/verify.sh" || :
ensure_file /usr/local/lib/jarvis/refresh-trusted-root 755 root:root \
  <"$repo/scripts/lib/refresh-trusted-root" || :
ensure_dir /var/lib/jarvis/attest 755 root:root
units=0
if ensure_file /etc/systemd/system/jarvis-attest-root.service 644 root:root <<EOF; then units=1; fi
# $MARK (#121)
[Unit]
Description=Refresh the Sigstore trusted root for verifying Jarvis releases
Documentation=https://github.com/faering/jarvis/blob/main/docs/pi-setup.md
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/lib/jarvis/refresh-trusted-root
ProtectSystem=strict
ReadWritePaths=/var/lib/jarvis/attest
PrivateTmp=yes
ProtectHome=yes
NoNewPrivileges=yes
EOF
if ensure_file /etc/systemd/system/jarvis-attest-root.timer 644 root:root <<EOF; then units=1; fi
# $MARK (#121)
[Unit]
Description=Refresh the Sigstore trusted root daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
((check || !units)) || systemctl daemon-reload
if [[ "$(unit_state jarvis-attest-root.timer)" != enabled ]]; then
  act "enable jarvis-attest-root.timer (daily)" systemctl enable --now jarvis-attest-root.timer
fi
if [[ ! -s "$(p /var/lib/jarvis/attest/trusted_root.jsonl)" ]]; then
  if ((check)); then
    log "DRIFT: /var/lib/jarvis/attest/trusted_root.jsonl (not fetched yet)"
    drift=$((drift + 1))
  else
    act "fetch the Sigstore trusted root" systemctl start jarvis-attest-root.service || :
    [[ -s "$(p /var/lib/jarvis/attest/trusted_root.jsonl)" ]] ||
      defer "trusted root: couldn't fetch it (network?); deploys refuse until it exists"
  fi
fi
units=0
if ensure_file /etc/systemd/system/jarvis-logs-prune.service 644 root:root <<EOF; then units=1; fi
# $MARK (#126)
[Unit]
Description=Prune Jarvis log files (older than 90 days, then down to the 20 GiB budget)
Documentation=https://github.com/faering/jarvis/blob/main/docs/logging.md
ConditionPathIsDirectory=$LOG_DIR

[Service]
Type=oneshot
ExecStart=/usr/local/bin/jarvis-logs prune --dir $LOG_DIR
# A throwaway user whose only write access is the log folder, through its group.
DynamicUser=yes
SupplementaryGroups=$LOG_GROUP
ReadWritePaths=$LOG_DIR
ProtectHome=yes
PrivateNetwork=yes
NoNewPrivileges=yes
Nice=10
IOSchedulingClass=idle
EOF
if ensure_file /etc/systemd/system/jarvis-logs-prune.timer 644 root:root <<EOF; then units=1; fi
# $MARK (#126)
[Unit]
Description=Prune Jarvis log files hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=5min
Persistent=true

[Install]
WantedBy=timers.target
EOF
((check || !units)) || systemctl daemon-reload
if [[ "$(unit_state jarvis-logs-prune.timer)" != enabled ]]; then
  act "enable jarvis-logs-prune.timer (hourly)" systemctl enable --now jarvis-logs-prune.timer
fi

# ---- 4d. network watchdog (#207, #212) -----------------------------------------------------
# About once a minute: if the Wi-Fi has lost the router, reconnect, restart NetworkManager,
# reload the driver, then reboot (scripts/pi/jarvis-netwatch).
section "network watchdog"
ensure_file /usr/local/lib/jarvis/netwatch 755 root:root <"$repo/scripts/pi/jarvis-netwatch" || :
units=0
if ensure_file /etc/systemd/system/jarvis-netwatch.service 644 root:root <<EOF; then units=1; fi
# $MARK (#207)
[Unit]
Description=Get the Wi-Fi back if the router stops answering
Documentation=https://github.com/faering/jarvis/blob/main/docs/pi-setup.md

[Service]
Type=oneshot
ExecStart=/usr/local/lib/jarvis/netwatch
# A run never blocks the next one: each step has a 45 s deadline, and this is the backstop.
TimeoutStartSec=150s
# The failed-check counter survives between runs (a oneshot's runtime dir is removed on
# exit); the last reboot's time survives reboots.
RuntimeDirectory=jarvis-netwatch
RuntimeDirectoryPreserve=yes
StateDirectory=jarvis-netwatch
ProtectSystem=strict
ReadWritePaths=$LOG_DIR
PrivateTmp=yes
ProtectHome=yes
NoNewPrivileges=yes
EOF
if ensure_file /etc/systemd/system/jarvis-netwatch.timer 644 root:root <<EOF; then units=1; fi
# $MARK (#207)
[Unit]
Description=Check the network 45 s after each check ends

[Timer]
OnBootSec=3min
OnUnitInactiveSec=45s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF
((check || !units)) || systemctl daemon-reload
if [[ "$(unit_state jarvis-netwatch.timer)" != enabled ]]; then
  act "enable jarvis-netwatch.timer (about once a minute)" systemctl enable --now jarvis-netwatch.timer
fi

# ---- 5. ssh hardening ----------------------------------------------------------------------
section "ssh"
ensure_enabled ssh.service
sshd_conf=/etc/ssh/sshd_config.d/10-jarvis.conf
if [[ ! -s "$(p "$op_home/.ssh/authorized_keys")" ]]; then
  # Key-only login with no key installed would lock you out.
  defer "ssh hardening: $operator has no ~/.ssh/authorized_keys (ssh-copy-id from your PC, then re-run)"
else
  backup="$tmpd/sshd.bak"
  had=0
  [[ -f "$(p "$sshd_conf")" ]] && cp -p "$(p "$sshd_conf")" "$backup" && had=1
  # 10- sorts before cloud-init's 50-cloud-init.conf; sshd uses the first value it reads.
  if ensure_file "$sshd_conf" 644 root:root <<EOF; then
# $MARK (#131)
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers $operator $DEPLOY_USER

# Root-owned key file for the deploy user (a Match in an included file ends with the file).
Match User $DEPLOY_USER
    AuthorizedKeysFile /etc/ssh/authorized_keys/%u
EOF
    if ! sshd -t; then
      if ((had)); then cp -p "$backup" "$(p "$sshd_conf")"; else rm -f "$(p "$sshd_conf")"; fi
      die "sshd -t rejected the new config; restored the previous one, sshd not reloaded"
    fi
    reload_if_active ssh reload
  fi
  # Verify what sshd actually uses (an earlier-sorting drop-in could override ours).
  eff="$(sshd -T 2>/dev/null || true)"
  effd="$(sshd -T -C "user=$DEPLOY_USER,host=localhost,addr=127.0.0.1" 2>/dev/null || true)"
  for want in "passwordauthentication no" "kbdinteractiveauthentication no" "permitrootlogin no"; do
    grep -qx "$want" <<<"$eff" || defer "sshd effective config lacks '$want' (another sshd_config.d file wins?)"
  done
  grep -qx "authorizedkeysfile /etc/ssh/authorized_keys/%u" <<<"$effd" ||
    grep -qx "authorizedkeysfile /etc/ssh/authorized_keys/$DEPLOY_USER" <<<"$effd" ||
    defer "sshd doesn't use /etc/ssh/authorized_keys for $DEPLOY_USER"
fi

# ---- 5b. wifi: stay connected (#206) --------------------------------------------------------
# On 2026-09-29 the Wi-Fi dropped, NetworkManager gave up after its 4 default attempts, and
# the Pi stayed offline all day. Global connection defaults (NetworkManager.conf), so the
# OS-generated netplan-* connection isn't edited; they apply where it doesn't set its own.
section "wifi"
if ensure_file /etc/NetworkManager/conf.d/10-jarvis-wifi.conf 644 root:root <<EOF; then
# $MARK (#206, #212)
[main]
# 0 = keep auto-connecting forever instead of giving up after 4 tries. It only works here:
# NetworkManager ignores connection.autoconnect-retries in a [connection] section.
autoconnect-retries-default=0

[connection-jarvis-wifi]
match-device=type:wifi
# 2 = disable Wi-Fi power saving: a dozing chip misses reconnects.
wifi.powersave=2
# 0 = retry the handshake forever. After 3 failures (e.g. a mesh kicking the Pi mid-
# handshake) NetworkManager asks for a new password; nobody can answer, so the connection
# fails with no-secrets and stays down.
connection.auth-retries=0
EOF
  reload_if_active NetworkManager reload
fi
# Raspberry Pi OS's Wi-Fi driver workarounds (/usr/lib/modprobe.d/rpi-brcmfmac.conf): no
# firmware roaming, no firmware WPA3/auth offload; both break on mesh networks. A custom
# file in /etc/modprobe.d can silently drop them, so report it (the fix depends on why).
if command -v modprobe >/dev/null; then
  brcm=" $(modprobe -c 2>/dev/null | sed -n 's/^options brcmfmac //p' | tr '\n' ' ') "
  for opt in roamoff=1 feature_disable=0x282000; do
    [[ "$brcm" == *" $opt "* ]] && continue
    ((check)) && drift=$((drift + 1))
    warn "Wi-Fi driver option $opt is not set (see: modprobe -c | grep brcmfmac)"
  done
fi
# Also now, without re-joining the network: NetworkManager applies the file on the next
# connect. Never in --check (power saving is runtime state, not drift).
if ((!check)) && command -v iw >/dev/null && iw dev wlan0 get power_save 2>/dev/null | grep -q ': on'; then
  act "Wi-Fi power saving off now (wlan0)" iw dev wlan0 set power_save off
fi

# ---- 6. firewall (nftables) ----------------------------------------------------------------
section "firewall"
nft_conf="$tmpd/nftables.conf"
# Only our own table: no `flush ruleset`, so Docker's and Tailscale's (iptables-nft) rules
# survive a reload. Docker publishes only on 127.0.0.1, which never reaches a LAN client.
cat >"$nft_conf" <<'EOF'
#!/usr/sbin/nft -f
# managed by jarvis scripts/pi/setup.sh; local edits are overwritten (#131)
# Inbound: deny by default. SSH only over Tailscale; the display talks to the agent on lo.
table inet jarvis
delete table inet jarvis
table inet jarvis {
	chain input {
		type filter hook input priority filter; policy drop;
		ct state established,related accept
		ct state invalid drop
		iif "lo" accept
		meta l4proto { icmp, ipv6-icmp } accept comment "ping, IPv6 neighbour discovery"
		ip6 saddr fe80::/10 udp dport 546 accept comment "DHCPv6 client"
		udp dport 41641 accept comment "Tailscale direct (peer-to-peer) connections"
		iifname "tailscale0" tcp dport 22 accept comment "SSH, tailnet only"
	}
}
EOF
ts_state="$(tailscale status --json 2>/dev/null | jq -r '.BackendState // empty' 2>/dev/null || true)"
if [[ "$ts_state" != Running && $check -eq 0 && -t 0 && -t 1 ]]; then
  log "Tailscale is not logged in: running 'tailscale up' (open the link it prints)"
  tailscale up --advertise-tags=tag:jarvis || warn "tailscale up failed"
  ts_state="$(tailscale status --json 2>/dev/null | jq -r '.BackendState // empty' 2>/dev/null || true)"
fi
if [[ "$ts_state" != Running ]]; then
  # SSH is allowed only on tailscale0: enabling this before Tailscale is up locks out LAN SSH.
  defer "firewall: Tailscale is not up (sudo tailscale up --advertise-tags=tag:jarvis), then re-run"
else
  nft -c -f "$nft_conf" || die "nft -c rejected the ruleset; nothing applied"
  fw=0
  ensure_file /etc/nftables.conf 755 root:root <"$nft_conf" && fw=1
  # Debian's unit flushes the WHOLE ruleset on stop (Docker's too); only drop our table.
  if ensure_file /etc/systemd/system/nftables.service.d/10-jarvis.conf 644 root:root <<EOF; then
# $MARK (#131)
[Service]
ExecStop=
ExecStop=/usr/sbin/nft delete table inet jarvis
EOF
    ((check)) || systemctl daemon-reload
  fi
  if ((!fake)) && ! nft list table inet jarvis >/dev/null 2>&1; then fw=1; fi
  if ((fw)); then act "load firewall (nft -f /etc/nftables.conf)" nft -f "$(p /etc/nftables.conf)"; fi
  ensure_enabled nftables.service
fi

# ---- 7. automatic security updates ---------------------------------------------------------
section "updates"
# Debian's 50unattended-upgrades already allows Debian stable point releases + security. Add
# the Pi archive (kernel, firmware: no separate security suite) and Tailscale (network-facing).
# Docker stays manual (`apt upgrade`): upgrading dockerd restarts the agent.
ensure_file /etc/apt/apt.conf.d/52jarvis-unattended-upgrades 644 root:root <<'EOF' || :
// managed by jarvis scripts/pi/setup.sh; local edits are overwritten (#131)
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
Unattended-Upgrade::Origins-Pattern {
	"origin=Raspberry Pi Foundation,codename=${distro_codename},label=Raspberry Pi Foundation";
	"origin=Tailscale,codename=${distro_codename},label=Tailscale";
};
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
// Reboot policy: only when an update requires it (kernel, libc), at 04:00, even if someone
// is logged in (the display session always is). Deploys never run then unless you approve one.
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
EOF
ensure_enabled apt-daily.timer
ensure_enabled apt-daily-upgrade.timer

# ---- 8. shell history ----------------------------------------------------------------------
section "shell history"
ensure_file /etc/profile.d/jarvis-history.sh 644 root:root <<EOF || :
# $MARK (#132)
# Bash history: large, timestamped, appended from every shell right away, kept on disk.
# Also sourced from ~/.bashrc (login shells read this file before ~/.bashrc resets it).
[ -n "\${BASH_VERSION:-}" ] || return 0
case \$- in *i*) ;; *) return 0 ;; esac
HISTSIZE=50000
HISTFILESIZE=100000
HISTTIMEFORMAT='%F %T  '
HISTCONTROL=ignoredups
shopt -s histappend
case ";\${PROMPT_COMMAND:-};" in
  *"history -a"*) ;;
  *) PROMPT_COMMAND="history -a\${PROMPT_COMMAND:+; \$PROMPT_COMMAND}" ;;
esac
EOF
hook='if [ -r /etc/profile.d/jarvis-history.sh ]; then . /etc/profile.d/jarvis-history.sh; fi # jarvis'
# Debian's ~/.bashrc sets HISTSIZE=1000/HISTFILESIZE=2000, and assigning HISTFILESIZE
# truncates the file at once: comment those out, then source ours at the end.
# (/etc/bash.bashrc is a dpkg conffile: editing it would hold back bash security updates.)
root_home="$(home_of root)"
for h in "$op_home" "${root_home:-/root}"; do
  rc="$(p "$h/.bashrc")"
  [[ -f "$rc" ]] || continue
  if grep -Eq '^(HISTSIZE|HISTFILESIZE|HISTCONTROL)=' "$rc"; then
    act "$h/.bashrc: comment out Debian's HISTSIZE/HISTFILESIZE/HISTCONTROL" \
      sed -i -E 's/^(HISTSIZE|HISTFILESIZE|HISTCONTROL)=/#jarvis: see \/etc\/profile.d\/jarvis-history.sh# &/' "$rc"
  fi
  # shellcheck disable=SC2016 # $1/$2 expand in the child bash
  grep -qxF "$hook" "$rc" || act "$h/.bashrc: source jarvis-history.sh" bash -c 'printf "%s\n" "$1" >>"$2"' _ "$hook" "$rc"
done

# ---- 8b. shell like the devcontainer (#214) --------------------------------------------------
# Prompt with the git branch, `ll`, and full vim as the editor: Raspberry Pi OS has only
# vim-tiny in vi-compatible mode (no -- INSERT --, arrow keys type letters).
section "shell"
ensure_file /etc/profile.d/jarvis-shell.sh 644 root:root <"$repo/scripts/pi/jarvis-shell.sh" || :
hook='if [ -r /etc/profile.d/jarvis-shell.sh ]; then . /etc/profile.d/jarvis-shell.sh; fi # jarvis'
for h in "$op_home" "${root_home:-/root}"; do
  rc="$(p "$h/.bashrc")"
  [[ -f "$rc" ]] || continue
  # shellcheck disable=SC2016 # $1/$2 expand in the child bash
  grep -qxF "$hook" "$rc" || act "$h/.bashrc: source jarvis-shell.sh" bash -c 'printf "%s\n" "$1" >>"$2"' _ "$hook" "$rc"
done
for alt in editor vi vim; do # nano outranks vim as `editor`; set all three explicitly
  [[ "$(readlink "$(p /etc/alternatives/$alt)" 2>/dev/null)" == /usr/bin/vim.basic ]] ||
    act "$alt -> vim" update-alternatives --quiet --set "$alt" /usr/bin/vim.basic
done

# ---- 9. unused services --------------------------------------------------------------------
section "services"
for u in "${UNUSED_UNITS[@]}"; do
  if [[ "$(unit_state "$u")" == enabled ]]; then act "disable $u" systemctl disable --now "$u"; fi
done
ensure_enabled bluetooth.service # the Bluetooth keyboard (#129)

# ---- summary -------------------------------------------------------------------------------
section "summary"
if ((check)); then
  ((drift == 0)) && log "no drift" && exit 0
  log "$drift item(s) drifted; run without --check to apply"
  exit 1
fi
log "applied $changes change(s)"
if ((${#deferred[@]})); then
  for d in "${deferred[@]}"; do warn "still to do: $d"; done
  exit 3
fi
