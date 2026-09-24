#!/usr/bin/env bash
# Release manifest for one component: the provenance + protocol facts deploy.yml relies on.
# release-artifacts.yml attaches it to the GitHub release as manifest.json, last, so its
# presence means every artifact of that release was published.
#
# Usage:  scripts/release/manifest.sh <agent|app> [image-repo]
set -euo pipefail

[[ $# -ge 1 && $# -le 2 ]] || {
  echo "usage: $(basename "$0") <agent|app> [image-repo]" >&2
  exit 2
}
component="$1"
image="${2:-}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

versions="$("$here/../version.sh" "$component")"
field() { sed -n "s/^$1=//p" <<<"$versions"; }
protocol="$("$here/protocol-version.sh" "$component")"

jq -n \
  --arg component "$component" \
  --arg version "$(field CANONICAL)" \
  --arg docker_tag "$(field DOCKER_TAG)" \
  --arg revision "$(field REVISION)" \
  --arg protocol "$protocol" \
  --arg image "$image" \
  '{component: $component, version: $version, docker_tag: $docker_tag, revision: $revision,
    protocol: (if $protocol == "none" then $protocol else ($protocol | tonumber) end)}
   + (if $image == "" then {} else {image: ($image + ":" + $docker_tag)} end)'
