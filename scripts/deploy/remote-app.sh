#!/usr/bin/env bash
# Runs ON THE PI (deploy.yml pipes it over ssh): install a released app .deb, verify the
# installed version, and reinstall the previous .deb on any failure.
#
# Usage:  remote-app.sh <deb-path> <expected-version> <protocol>
#         <deb-path> is the staged candidate (deploy.yml: $JARVIS_DIR/incoming/). It is
#         removed afterwards, and promoted to app/current.deb only once installed.
# Env:    JARVIS_DIR (default ~/jarvis). Needs passwordless sudo for
#         /usr/local/sbin/jarvis-install-app only (docs/pi-setup.md).
# State:  $JARVIS_DIR/state/app.env (read by the compat gate). The installed .deb is kept as
#         app/current.deb (the next deploy's rollback target), the one before as previous.deb.
set -euo pipefail

[[ $# -eq 3 ]] || {
  echo "usage: $(basename "$0") <deb-path> <expected-version> <protocol>" >&2
  exit 2
}
expected="$2" protocol="$3"
dir="${JARVIS_DIR:-$HOME/jarvis}"
state="$dir/state/app.env"
current="$dir/app/current.deb"
previous="$dir/app/previous.deb"

log() { echo "[app-deploy] $*"; }
state_get() { [[ -f "$1" ]] && sed -n "s/^$2=//p" "$1" | tail -n1 || true; }
installed() { dpkg-query -W -f='${Status} ${Version}' "$1" 2>/dev/null | sed -n 's/^install ok installed //p'; }
install() { sudo -n /usr/local/sbin/jarvis-install-app "$1"; }
keep() { cp -f "$1" "$2.tmp" && mv -f "$2.tmp" "$2"; } # keep <src> <dest>, atomically

mkdir -p "$dir/state" "$dir/app"
deb="$(realpath "$1")" # apt-get wants a path, not a bare file name
prev_deb="$(state_get "$state" DEB)"
prev_version="$(state_get "$state" VERSION)"
# Never install from a kept .deb's path: the candidate would overwrite the rollback target.
for kept in "$current" "$previous" "${prev_deb:-/nonexistent}"; do
  if [[ "$deb" -ef "$kept" ]]; then
    log "$deb is a kept rollback .deb; stage the candidate elsewhere (e.g. $dir/incoming/)"
    exit 1
  fi
done
trap 'rm -f "$deb"' EXIT

pkg="$(dpkg-deb -f "$deb" Package)"
deb_version="$(dpkg-deb -f "$deb" Version)"
if [[ "$deb_version" != "$expected" ]]; then
  log "$deb is version '$deb_version', expected '$expected'"
  exit 1
fi

log "installing $pkg $expected (previous: ${prev_version:-none})"
if install "$deb" && [[ "$(installed "$pkg")" == "$expected" ]]; then
  # Promote only now: the old current becomes previous, the candidate becomes current.
  prev_kept=""
  if [[ -n "$prev_deb" && -f "$prev_deb" ]]; then
    keep "$prev_deb" "$previous"
    prev_kept="$previous"
  fi
  keep "$deb" "$current"
  # Write the new state beside the old one and rename it into place (atomic): a lost SSH
  # session or power cut mid-write must never leave an empty state file.
  cat >"$state.next" <<EOF
PACKAGE=$pkg
VERSION=$expected
PROTOCOL=$protocol
DEB=$current
PREVIOUS_DEB=$prev_kept
PREVIOUS_VERSION=$prev_version
DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
  mv -f "$state.next" "$state"
  # Prune anything else (e.g. debs kept under their release names by older deploys).
  find "$dir/app" -maxdepth 1 -name '*.deb' ! -path "$current" ! -path "$previous" -delete
  [[ -n "$prev_kept" ]] || rm -f "$previous"
  log "installed $pkg $expected; it takes effect on the next app start"
  exit 0
fi

log "FAILED (installed: '$(installed "$pkg")')"
if [[ -n "$prev_deb" && -f "$prev_deb" ]]; then
  log "rolling back to $prev_version"
  if install "$prev_deb" && [[ "$(installed "$pkg")" == "$prev_version" ]]; then
    log "rolled back to app $prev_version"
  else
    log "ROLLBACK FAILED too; the app needs manual attention"
  fi
fi
exit 1
