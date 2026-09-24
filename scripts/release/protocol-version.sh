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
schema="$root/packages/protocol/protocol.schema.json"

case "$1" in
  agent) files=("$root/agent/src/jarvis_agent/protocol.py") ;;
  app)
    # The app speaks @jarvis/protocol, whose schema is the source of truth (#32).
    if [[ -f "$schema" ]]; then
      v="$(jq -er '.properties.v.const | numbers' "$schema")" || {
        echo "properties.v.const not found in $schema" >&2
        exit 1
      }
      echo "$v"
      exit 0
    fi
    # Tags before #32 kept the contract in the app itself.
    files=("$root/frontend/src/agent/protocol.ts")
    ;;
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
