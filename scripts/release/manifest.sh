#!/usr/bin/env bash
# Release manifest for one component: the provenance + protocol facts deploy.yml relies on.
# release-artifacts.yml attaches it to the GitHub release as manifest.json, last, so its
# presence means every artifact of that release was published.
#
# Usage:  [IMAGE_DIGEST=sha256:<64 hex>] scripts/release/manifest.sh <agent|app> [image-repo]
# With a digest, the manifest also pins the image by it (the Pi verifies and pulls that).
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
digest="${IMAGE_DIGEST:-}"
if [[ -n "$digest" && ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "manifest.sh: IMAGE_DIGEST '$digest' is not sha256:<64 hex>" >&2
  exit 2
fi

jq -n \
  --arg component "$component" \
  --arg version "$(field CANONICAL)" \
  --arg docker_tag "$(field DOCKER_TAG)" \
  --arg revision "$(field REVISION)" \
  --arg protocol "$protocol" \
  --arg image "$image" \
  --arg digest "$digest" \
  '{component: $component, version: $version, docker_tag: $docker_tag, revision: $revision,
    protocol: (if $protocol == "none" then $protocol else ($protocol | tonumber) end)}
   + (if $image == "" then {} else {image: ($image + ":" + $docker_tag)} end)
   + (if $digest == "" then {} else {digest: $digest} end)'
