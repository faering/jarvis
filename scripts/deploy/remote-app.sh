#!/usr/bin/env bash
# Runs ON THE PI (deploy.yml pipes it over ssh): install a released app .deb, verify the
# installed version, and reinstall the previous .deb on any failure.
#
# Usage:  remote-app.sh <deb-path> <expected-version> <protocol>
# Env:    JARVIS_DIR (default ~/jarvis). Needs passwordless `sudo apt-get`.
# State:  $JARVIS_DIR/state/app.env (read by the compat gate); debs kept in $JARVIS_DIR/app/.
set -euo pipefail

[[ $# -eq 3 ]] || {
  echo "usage: $(basename "$0") <deb-path> <expected-version> <protocol>" >&2
  exit 2
}
deb="$1" expected="$2" protocol="$3"
dir="${JARVIS_DIR:-$HOME/jarvis}"
state="$dir/state/app.env"

log() { echo "[app-deploy] $*"; }
state_get() { [[ -f "$1" ]] && sed -n "s/^$2=//p" "$1" | tail -n1 || true; }
installed() { dpkg-query -W -f='${Status} ${Version}' "$1" 2>/dev/null | sed -n 's/^install ok installed //p'; }
install() { sudo -n apt-get install -y --allow-downgrades "$1"; }

mkdir -p "$dir/state" "$dir/app"
pkg="$(dpkg-deb -f "$deb" Package)"
deb_version="$(dpkg-deb -f "$deb" Version)"
if [[ "$deb_version" != "$expected" ]]; then
  log "$deb is version '$deb_version', expected '$expected'"
  exit 1
fi
# Keep the .deb: it is the rollback target of the next deploy.
kept="$dir/app/$(basename "$deb")"
[[ "$deb" -ef "$kept" ]] || cp "$deb" "$kept"

prev_deb="$(state_get "$state" DEB)"
prev_version="$(state_get "$state" VERSION)"
log "installing $pkg $expected (previous: ${prev_version:-none})"
if install "$kept" && [[ "$(installed "$pkg")" == "$expected" ]]; then
  cat >"$state" <<EOF
PACKAGE=$pkg
VERSION=$expected
PROTOCOL=$protocol
DEB=$kept
PREVIOUS_DEB=$prev_deb
DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
  # Prune debs other than the current and previous release.
  find "$dir/app" -maxdepth 1 -name '*.deb' ! -path "$kept" ! -path "${prev_deb:-/nonexistent}" -delete
  log "installed $pkg $expected; it takes effect on the next app start"
  exit 0
fi

log "FAILED (installed: '$(installed "$pkg")')"
[[ "$kept" -ef "$prev_deb" ]] || rm -f "$kept"
if [[ -n "$prev_deb" && -f "$prev_deb" ]]; then
  log "rolling back to $prev_version"
  if install "$prev_deb" && [[ "$(installed "$pkg")" == "$prev_version" ]]; then
    log "rolled back to app $prev_version"
  else
    log "ROLLBACK FAILED too; the app needs manual attention"
  fi
fi
exit 1
