#!/usr/bin/env bash
# Run the GitHub Actions workflows locally with `act` before pushing, so we catch
# failures without waiting on remote status checks.
#
# Usage:
#   scripts/ci-local.sh            # run the push-event workflows
#   scripts/ci-local.sh -l         # list jobs
#   scripts/ci-local.sh -j lint    # run a single job
#   scripts/ci-local.sh <act args> # any extra args are passed straight to act
set -euo pipefail

if ! command -v act >/dev/null 2>&1; then
  echo "error: 'act' is not installed (expected in the devcontainer image)." >&2
  exit 1
fi

if [ ! -d .github/workflows ]; then
  echo "note: no .github/workflows yet — nothing to run (see backlog E1)." >&2
  exit 0
fi

# medium image keeps parity with GitHub-hosted runners without the huge :full image.
# With no args, run the default `push` event.
exec act \
  -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest \
  "${@:-push}"
