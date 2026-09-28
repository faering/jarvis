#!/usr/bin/env bash
# Agent <-> app integration test (#108): the app's real AgentClient against a live agent
# (frontend/integration/). Runs three pairs:
#   1. this agent (compose, built with provenance)  x  this app's client
#   2. this agent                                   x  the latest released app's client
#   3. the latest released agent image              x  this app's client
# 2 and 3 are skipped (with a notice) when there is no such release yet. A pair whose
# protocols differ must stop cleanly at the client's `incompatible` state instead.
# IT_RELEASED_PAIR=1 runs only IT_AGENT_REF's published image x IT_APP_REF's client: a
# Jarvis release's pinned set (#162). There an unpullable image fails instead of building.
#
# Usage:  scripts/integration-test.sh
# Env:    IT_NETWORK=1   reach the agent over jarvis-net by container name (devcontainer)
#                        instead of 127.0.0.1:8000 (CI)
#         IT_AGENT_REF / IT_APP_REF   "released" refs to test against (default: newest
#                        agent-v* / app-v* tag)
#         IT_RELEASED_PAIR=1  only released agent x released app (both refs required)
#         IT_AGENT_IMAGE registry repo of released agents (default ghcr.io/faering/jarvis-agent)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "$root/docker-compose.yml" -p jarvis-it)
released=jarvis-it-released-agent
registry="${IT_AGENT_IMAGE:-ghcr.io/faering/jarvis-agent}"
work="$(mktemp -d)"
created_network=false

cleanup() {
  "${compose[@]}" down --volumes >/dev/null 2>&1 || true
  docker rm -f "$released" >/dev/null 2>&1 || true
  if [[ "$created_network" == true ]]; then docker network rm jarvis-net >/dev/null 2>&1 || true; fi
  rm -rf "$work"
}
trap cleanup EXIT

# jarvis-net normally comes from the devcontainer's initializeCommand; CI creates it.
if ! docker network inspect jarvis-net >/dev/null 2>&1; then
  docker network create jarvis-net >/dev/null
  created_network=true
fi

ws_url() { # <container name>
  if [[ "${IT_NETWORK:-}" == 1 ]]; then echo "ws://$1:8000/ws"; else echo "ws://127.0.0.1:8000/ws"; fi
}
released_ref() { # <component>: override, else the newest release tag
  local override="IT_${1^^}_REF"
  if [[ -n "${!override:-}" ]]; then echo "${!override}"; else
    git -C "$root" tag --list "$1-v*" --sort=-v:refname | head -n1
  fi
}
export_tree() { # <ref> <dir>: the ref's sources, without a checkout
  mkdir -p "$2"
  git -C "$root" archive "$1" | tar -x -C "$2"
}
protocol() { "$root/scripts/release/protocol-version.sh" "$@"; }

# run_suite <label> <ws url> <expected agent version> <agent protocol> <app protocol> [client.ts]
run_suite() {
  local incompatible=0
  [[ "$4" != "$5" ]] && incompatible=1
  echo "::group::$1 (protocol: agent $4, app $5)"
  AGENT_WS_URL="$2" AGENT_EXPECT_VERSION="$3" AGENT_EXPECT_INCOMPATIBLE="$incompatible" \
    AGENT_CLIENT_MODULE="${6:-}" pnpm --dir "$root/frontend" test:integration
  echo "::endgroup::"
}

# released_app <ref>: export an app release and install its deps. Sets released_client
# (empty when that release has no agent client) and released_app_proto.
released_app() {
  export_tree "$1" "$work/app"
  released_client="$work/app/frontend/src/agent/client.ts"
  released_app_proto="$(protocol app "$work/app")"
  if [[ ! -f "$released_client" || "$released_app_proto" == none ]]; then
    released_client=""
    return 0
  fi
  # The released client resolves its own dependencies, not this checkout's.
  pnpm --dir "$work/app" install --frozen-lockfile --ignore-scripts --reporter=silent
}

this_agent_suites() { # pairs 1 and 2
  echo "::group::build + start this agent (compose)"
  local canonical url app_ref
  canonical="$("$root/scripts/version.sh" agent | sed -n 's/^CANONICAL=//p')"
  "$root/scripts/compose-build.sh"
  "${compose[@]}" up --detach --wait --wait-timeout 60 agent
  echo "::endgroup::"
  url="$(ws_url jarvis-it-agent-1)"

  run_suite "this agent x this app" "$url" "$canonical" "$agent_proto" "$app_proto"

  app_ref="$(released_ref app)"
  if [[ -z "$app_ref" ]]; then
    echo "::notice::No app release yet; skipped this agent x released app."
  else
    released_app "$app_ref"
    if [[ -z "$released_client" ]]; then
      echo "::notice::App $app_ref has no agent client; skipped this agent x released app."
    else
      run_suite "this agent x app $app_ref" "$url" "$canonical" \
        "$agent_proto" "$released_app_proto" "$released_client"
    fi
  fi
  "${compose[@]}" down --volumes
}

agent_proto="$(protocol agent)"
app_proto="$(protocol app)"
# The app side of pair 3: this app, or (IT_RELEASED_PAIR=1) the pinned released app.
app_label="this app" app_client=""

if [[ "${IT_RELEASED_PAIR:-}" == 1 ]]; then
  if [[ -z "${IT_AGENT_REF:-}" || -z "${IT_APP_REF:-}" ]]; then
    echo "::error::IT_RELEASED_PAIR=1 needs IT_AGENT_REF and IT_APP_REF."
    exit 2
  fi
  released_app "$IT_APP_REF"
  if [[ -z "$released_client" ]]; then
    echo "::error::App $IT_APP_REF has no agent client to test."
    exit 1
  fi
  app_label="app $IT_APP_REF" app_client="$released_client" app_proto="$released_app_proto"
else
  this_agent_suites
fi

# --- the released agent -----------------------------------------------------------------
agent_ref="$(released_ref agent)"
if [[ -z "$agent_ref" ]]; then
  echo "::notice::No agent release yet; skipped released agent x this app."
  exit 0
fi
export_tree "$agent_ref" "$work/agent"
version="" # only a release tag pins the version (and the published image)
[[ "$agent_ref" =~ ^agent-v([0-9]+\.[0-9]+\.[0-9]+)$ ]] && version="${BASH_REMATCH[1]}"
echo "::group::start agent $agent_ref"
image="$registry:$version"
pulled=false
if [[ -n "$version" ]] && docker pull --quiet "$image"; then pulled=true; fi
if [[ "$pulled" == false && "${IT_RELEASED_PAIR:-}" == 1 ]]; then
  echo "::error::$image is not pullable; a Jarvis release pins published images only."
  exit 1
elif [[ "$pulled" == false ]]; then
  # Not published (or not pullable here): build the tag's own sources instead.
  echo "::notice::$image is not pullable; testing $agent_ref built from its tagged sources."
  image="jarvis-it-released:${version:-dev}"
  docker build --quiet --build-arg VERSION="$version" \
    --build-arg REVISION="$(git -C "$root" rev-parse "$agent_ref^{commit}")" \
    -t "$image" "$work/agent/agent"
fi
publish=(-p 127.0.0.1:8000:8000)
[[ "${IT_NETWORK:-}" == 1 ]] && publish=()
docker run --detach --name "$released" --network jarvis-net "${publish[@]}" "$image" >/dev/null
for _ in $(seq 60); do
  status="$(docker inspect --format '{{.State.Health.Status}}' "$released")"
  [[ "$status" == healthy ]] && break
  sleep 1
done
[[ "$status" == healthy ]] || {
  docker logs "$released"
  echo "::error::$agent_ref did not turn healthy (status: $status)."
  exit 1
}
echo "::endgroup::"

run_suite "agent $agent_ref x $app_label" "$(ws_url "$released")" "$version" \
  "$(protocol agent "$work/agent")" "$app_proto" "$app_client"
