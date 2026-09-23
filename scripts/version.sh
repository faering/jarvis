#!/usr/bin/env bash
# Build provenance for one component (see AGENTS.md "Build provenance & displayed versions").
#
# Usage:  scripts/version.sh <agent|app>
#   eval "$(scripts/version.sh agent)"          # sets CANONICAL, DOCKER_TAG, REVISION
#   scripts/version.sh agent >> "$GITHUB_ENV"   # in GitHub Actions
#
# Output (KEY=VALUE, one per line):
#   CANONICAL   strict SemVer: 1.2.3 | 1.2.3+<ahead>.g<sha>[.dirty]
#   DOCKER_TAG  no '+':        1.2.3 | 1.2.3-<ahead>-g<sha>[-dirty]
#   REVISION    full commit sha of HEAD
# With no <component>-v* tag yet, the base is 0.0.0 and <ahead> is the total commit count.
#
# NOTE: CI checkouts need full history + tags (actions/checkout `fetch-depth: 0`);
# a shallow clone has no tags and always yields 0.0.0.
set -euo pipefail

usage() {
  echo "usage: $(basename "$0") <agent|app>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
component="$1"
case "$component" in
  agent | app) ;;
  *) usage ;;
esac

desc="$(git describe --tags --match "${component}-v*" --long --always --dirty)"
revision="$(git rev-parse HEAD)"

dirty=false
if [[ "$desc" == *-dirty ]]; then
  dirty=true
  desc="${desc%-dirty}"
fi

if [[ "$desc" =~ ^${component}-v(.+)-([0-9]+)-g([0-9a-f]+)$ ]]; then
  base="${BASH_REMATCH[1]}"
  ahead="${BASH_REMATCH[2]}"
  sha="${BASH_REMATCH[3]}"
else
  # --always fell back to a bare abbreviated sha: no tag for this component yet.
  base="0.0.0"
  ahead="$(git rev-list --count HEAD)"
  sha="$desc"
fi

if [[ "$ahead" == 0 && "$dirty" == false ]]; then
  canonical="$base"
  docker_tag="$base"
else
  canonical="${base}+${ahead}.g${sha}"
  docker_tag="${base}-${ahead}-g${sha}"
  if [[ "$dirty" == true ]]; then
    canonical+=".dirty"
    docker_tag+="-dirty"
  fi
fi

printf 'CANONICAL=%s\nDOCKER_TAG=%s\nREVISION=%s\n' "$canonical" "$docker_tag" "$revision"
