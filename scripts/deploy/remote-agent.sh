#!/usr/bin/env bash
# Runs ON THE PI (deploy.yml pipes it over ssh): roll the agent to a released image,
# verify it, and roll back to the previous image on any failure.
#
# Usage:  remote-agent.sh <docker-tag> <expected-version> <protocol>
# Env:    JARVIS_DIR (default ~/jarvis; holds docker-compose.yml from deploy/pi/)
#         AGENT_IMAGE (default ghcr.io/faering/jarvis-agent), AGENT_HEALTH_TIMEOUT (s, 120)
#         AGENT_PORT (host port, default 8000)
# State:  $JARVIS_DIR/state/agent.env (compose --env-file; also read by the compat gate)
set -euo pipefail

[[ $# -eq 3 ]] || {
  echo "usage: $(basename "$0") <docker-tag> <expected-version> <protocol>" >&2
  exit 2
}
tag="$1" expected="$2" protocol="$3"
dir="${JARVIS_DIR:-$HOME/jarvis}"
image="${AGENT_IMAGE:-ghcr.io/faering/jarvis-agent}"
timeout="${AGENT_HEALTH_TIMEOUT:-120}"
state="$dir/state/agent.env"
next="$dir/state/agent.env.next"

log() { echo "[agent-deploy] $*"; }
state_get() { [[ -f "$1" ]] && sed -n "s/^$2=//p" "$1" | tail -n1 || true; }
compose() { # compose <env-file> <args...>
  local env="$1"
  shift
  AGENT_PORT="${AGENT_PORT:-8000}" docker compose --project-directory "$dir" \
    -f "$dir/docker-compose.yml" --env-file "$env" "$@"
}

# Healthy container + OCI version label (+ /version, once the agent serves it) == expected.
verify() { # verify <env-file> <expected-version>
  local env="$1" want="$2" cid health label body deadline=$((SECONDS + timeout))
  while :; do
    cid="$(compose "$env" ps -q agent)"
    health="$([[ -n "$cid" ]] && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" || echo missing)"
    case "$health" in
      healthy) break ;;
      unhealthy)
        log "container is unhealthy"
        return 1
        ;;
    esac
    if ((SECONDS >= deadline)); then
      log "not healthy after ${timeout}s (status: $health)"
      return 1
    fi
    sleep 2
  done
  label="$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$cid")"
  if [[ "$label" != "$want" ]]; then
    log "image version label is '$label', expected '$want'"
    return 1
  fi
  # /version lands with #28; until then a 404 just skips this check.
  body="$(docker exec "$cid" python -c '
import sys, urllib.error, urllib.request
try:
    print(urllib.request.urlopen("http://127.0.0.1:8000/version", timeout=3).read().decode())
except urllib.error.HTTPError as e:
    sys.exit(0 if e.code == 404 else 1)
')" || {
    log "/version request failed"
    return 1
  }
  if [[ -n "$body" && "$body" != *"\"$want\""* ]]; then
    log "/version reports '$body', expected '$want'"
    return 1
  fi
  log "healthy, version $want"
}

mkdir -p "$dir/state"
[[ -f "$dir/docker-compose.yml" ]] || {
  log "missing $dir/docker-compose.yml (deploy/pi/docker-compose.yml)"
  exit 1
}
docker network inspect jarvis-net >/dev/null 2>&1 || docker network create jarvis-net >/dev/null

prev_tag="$(state_get "$state" AGENT_IMAGE_TAG)"
prev_version="$(state_get "$state" VERSION)"
cat >"$next" <<EOF
AGENT_IMAGE=$image
AGENT_IMAGE_TAG=$tag
VERSION=$expected
PROTOCOL=$protocol
PREVIOUS_IMAGE_TAG=$prev_tag
DEPLOYED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

log "deploying $image:$tag (previous: ${prev_tag:-none})"
if compose "$next" pull agent && compose "$next" up -d agent && verify "$next" "$expected"; then
  mv "$next" "$state"
  log "deployed agent $expected"
  exit 0
fi

rm -f "$next"
if [[ -z "$prev_tag" ]]; then
  log "FAILED and there is no previous release to roll back to"
  exit 1
fi
log "FAILED; rolling back to $prev_tag"
compose "$state" up -d agent
if verify "$state" "$prev_version"; then
  log "rolled back to agent $prev_version"
else
  log "ROLLBACK FAILED too; the agent needs manual attention"
fi
exit 1
