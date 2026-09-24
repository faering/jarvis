#!/usr/bin/env bash
# Runs ON THE PI: print a component's deployed VERSION and PROTOCOL (KEY=VALUE), or nothing
# when it was never deployed. The compat gate in deploy.yml reads this.
#
# Usage:  remote-state.sh <agent|app>      Env: JARVIS_DIR (default ~/jarvis)
set -euo pipefail

[[ $# -eq 1 && "$1" =~ ^(agent|app)$ ]] || {
  echo "usage: $(basename "$0") <agent|app>" >&2
  exit 2
}
state="${JARVIS_DIR:-$HOME/jarvis}/state/$1.env"
[[ -f "$state" ]] || exit 0
grep -E '^(VERSION|PROTOCOL)=' "$state" || true
