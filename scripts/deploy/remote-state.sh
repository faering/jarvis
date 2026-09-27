#!/usr/bin/env bash
# Runs ON THE PI as the deploy user: print a component's deployed VERSION and PROTOCOL
# (KEY=VALUE), or nothing when it was never deployed. The compat gate in deploy.yml reads this.
# The agent's state is root-owned (/var/lib/jarvis), so it is read via jarvis-deploy-agent.
#
# Usage:  remote-state.sh <agent|app>      Env: JARVIS_DIR (default ~/jarvis; app state)
set -euo pipefail

[[ $# -eq 1 && "$1" =~ ^(agent|app)$ ]] || {
  echo "usage: $(basename "$0") <agent|app>" >&2
  exit 2
}
if [[ "$1" == agent ]]; then
  # No `|| true`: if sudo isn't set up, fail the gate instead of reading "not deployed".
  state="$(sudo -n /usr/local/sbin/jarvis-deploy-agent state)"
else
  file="${JARVIS_DIR:-$HOME/jarvis}/state/app.env"
  [[ -f "$file" ]] || exit 0
  state="$(cat "$file")"
fi
grep -E '^(VERSION|PROTOCOL)=' <<<"$state" || true
