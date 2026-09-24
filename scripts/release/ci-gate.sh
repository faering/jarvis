#!/usr/bin/env bash
# Release gate: wait for the commit's `ci-ok` check-run and fail unless it succeeded,
# so broken code is never built into a release artifact (and so never deployed).
#
# Usage:  scripts/release/ci-gate.sh <sha>
# Env:    GH_TOKEN + GITHUB_REPOSITORY (set in Actions); CI_GATE_TIMEOUT seconds (default 3600)
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $(basename "$0") <sha>" >&2
  exit 2
}
sha="$1"
repo="${GITHUB_REPOSITORY:?}"
timeout="${CI_GATE_TIMEOUT:-3600}"
deadline=$((SECONDS + timeout))

# release-please publishes the release while the release commit's own CI is still running.
while :; do
  # The newest run wins. Sort by id (monotonic), not started_at: a queued re-run has
  # started_at null and would otherwise lose to an older completed run.
  result="$(gh api "repos/$repo/commits/$sha/check-runs?check_name=ci-ok&filter=all" \
    --jq '[.check_runs[]] | sort_by(.id) | last // {} | "\(.status // "missing") \(.conclusion // "-")"')"
  read -r status conclusion <<<"$result"
  if [[ "$status" == completed ]]; then
    if [[ "$conclusion" == success ]]; then
      echo "ci-ok passed for $sha"
      exit 0
    fi
    echo "::error::ci-ok concluded '$conclusion' for $sha; refusing to release it."
    exit 1
  fi
  if ((SECONDS >= deadline)); then
    echo "::error::ci-ok for $sha is still '$status' after ${timeout}s."
    exit 1
  fi
  echo "ci-ok for $sha is '$status'; waiting..."
  sleep 30
done
