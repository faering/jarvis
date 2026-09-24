#!/usr/bin/env bash
# WebSocket protocol version a component speaks, read from its source (run at the release tag).
#
# Usage:  scripts/release/protocol-version.sh <agent|app>
# Prints an integer, or "none" when the component has no protocol client/server yet.
set -euo pipefail

[[ $# -eq 1 ]] || {
  echo "usage: $(basename "$0") <agent|app>" >&2
  exit 2
}
root="$(git rev-parse --show-toplevel)"

case "$1" in
  agent) files=("$root/agent/src/jarvis_agent/protocol.py") ;;
  # packages/protocol (#32) supersedes the app-local copy once it lands.
  app) files=("$root/packages/protocol/src/index.ts" "$root/frontend/src/agent/protocol.ts") ;;
  *)
    echo "unknown component: $1" >&2
    exit 2
    ;;
esac

for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  v="$(sed -nE 's/^(export const )?PROTOCOL_VERSION( *: *[a-z]+)? *= *([0-9]+);?$/\3/p' "$f" | head -n1)"
  if [[ -n "$v" ]]; then
    echo "$v"
    exit 0
  fi
  echo "PROTOCOL_VERSION not found in $f" >&2
  exit 1
done
echo none
