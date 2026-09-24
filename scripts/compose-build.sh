#!/usr/bin/env bash
# Build the agent image with build provenance baked in (GET /version + OCI labels).
#
# Usage:  scripts/compose-build.sh [docker compose build options]
#   then  docker compose up -d        # not `up --build`: that rebuilds without provenance
#
# Tags the image jarvis-agent:dev (compose) and jarvis-agent:<DOCKER_TAG>.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
eval "$("$root/scripts/version.sh" agent)"

export JARVIS_VERSION="$CANONICAL"
export JARVIS_REVISION="$REVISION"
JARVIS_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export JARVIS_BUILD_TIME

docker compose -f "$root/docker-compose.yml" build "$@" agent
docker tag jarvis-agent:dev "jarvis-agent:$DOCKER_TAG"
echo "built jarvis-agent:$DOCKER_TAG (version $CANONICAL)"
