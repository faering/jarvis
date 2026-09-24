#!/usr/bin/env bash
# Build the agent image with build provenance baked in (GET /version + OCI labels).
#
# Usage:  scripts/compose-build.sh [docker compose build options]
#   then  docker compose up -d        # not `up --build`: that rebuilds without provenance
#
# Tags the image jarvis-agent:dev (compose) and jarvis-agent:<DOCKER_TAG>.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parse version.sh's KEY=VALUE lines without eval: the values derive from tag text, so
# evaluating them could run commands. Unknown keys and unexpected characters abort.
CANONICAL="" DOCKER_TAG="" REVISION=""
fail() {
  echo "compose-build: $*" >&2
  exit 1
}
output="$("$root/scripts/version.sh" agent)"
while IFS= read -r line; do
  [[ "$line" == *=* ]] || fail "unexpected version.sh output: $line"
  key="${line%%=*}"
  value="${line#*=}"
  case "$key" in
    CANONICAL) pattern='^[0-9A-Za-z.+-]+$' ;;
    DOCKER_TAG) pattern='^[0-9A-Za-z_][0-9A-Za-z_.-]{0,127}$' ;;
    REVISION) pattern='^[0-9a-f]{40,64}$' ;;
    *) fail "unexpected version.sh key: $key" ;;
  esac
  [[ "$value" =~ $pattern ]] || fail "unexpected characters in $key: $value"
  printf -v "$key" '%s' "$value"
done <<<"$output"
[[ -n "$CANONICAL" && -n "$DOCKER_TAG" && -n "$REVISION" ]] ||
  fail "version.sh did not emit CANONICAL, DOCKER_TAG and REVISION"

export JARVIS_VERSION="$CANONICAL"
export JARVIS_REVISION="$REVISION"
JARVIS_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export JARVIS_BUILD_TIME

docker compose -f "$root/docker-compose.yml" build "$@" agent
docker tag jarvis-agent:dev "jarvis-agent:$DOCKER_TAG"
echo "built jarvis-agent:$DOCKER_TAG (version $CANONICAL)"
