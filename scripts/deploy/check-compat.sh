#!/usr/bin/env bash
# Deploy gate: may <component>@<version> run next to the other component's deployed release?
#
# Usage:  scripts/deploy/check-compat.sh <compatibility.json> <agent|app> <version> <protocol> \
#                                        <other-version> <other-protocol>
# Pass "" as other-version when the other component is not deployed.
# Protocols are integers or "none" (the component has no WebSocket endpoint/client yet).
#
# Rule, first match wins (see COMPATIBILITY.md):
#   1. other component not deployed           -> ok
#   2. pair in "blocked"                      -> refuse
#   3. pair in "known_good"                   -> ok (verified on a real Pi)
#   4. either side speaks protocol "none"     -> ok (nothing to disagree on)
#   5. same WebSocket protocol version        -> ok, otherwise refuse
set -euo pipefail

[[ $# -eq 6 ]] || {
  echo "usage: $(basename "$0") <compatibility.json> <agent|app> <version> <protocol> <other-version> <other-protocol>" >&2
  exit 2
}
file="$1" component="$2" version="$3" protocol="$4" other_version="$5" other_protocol="$6"

case "$component" in
  agent) agent="$version" app="$other_version" agent_p="$protocol" app_p="$other_protocol" ;;
  app) agent="$other_version" app="$version" agent_p="$other_protocol" app_p="$protocol" ;;
  *)
    echo "unknown component: $component" >&2
    exit 2
    ;;
esac
pair="agent $agent + app $app"

ok() {
  echo "compatible: $pair ($1)"
  exit 0
}
refuse() {
  echo "::error::incompatible: $pair ($1); see COMPATIBILITY.md"
  exit 1
}

[[ -n "$other_version" ]] || ok "other component not deployed"

listed() { # listed <key>
  jq -e --arg a "$agent" --arg p "$app" \
    --arg k "$1" '.[$k] // [] | any(.agent == $a and .app == $p)' "$file" >/dev/null
}
listed blocked && refuse "listed in blocked"
listed known_good && ok "listed in known_good"
[[ "$agent_p" == none || "$app_p" == none ]] && ok "no shared protocol yet"
[[ "$agent_p" == "$app_p" ]] && ok "both speak protocol $agent_p"
refuse "agent speaks protocol $agent_p, app speaks $app_p"
