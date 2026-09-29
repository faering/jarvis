#!/usr/bin/env bash
# Tests for scripts/pi/jarvis-netwatch with nmcli, ip, ping and systemctl stubbed.
# Usage: scripts/pi/test_netwatch.sh   (exits non-zero on any failure)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin" STUB="$tmp/stub"
mkdir -p "$bin" "$STUB"
stub() { cat >"$bin/$1" && chmod +x "$bin/$1"; }
# Scenario knobs in $STUB: wifi (device name, empty = none), route, gw_ok (ping answers).
stub nmcli <<'EOF'
#!/usr/bin/env bash
case "$*" in
  "-t -f DEVICE,TYPE device") [[ -s "$STUB/wifi" ]] && echo "$(cat "$STUB/wifi"):wifi"; echo "eth0:ethernet" ;;
  "device connect "*) echo "nmcli $*" >>"$STUB/calls" ;;
esac
EOF
stub ip <<'EOF'
#!/usr/bin/env bash
cat "$STUB/route" 2>/dev/null
EOF
stub ping <<'EOF'
#!/usr/bin/env bash
[[ -e "$STUB/gw_ok" ]]
EOF
stub systemctl <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$STUB/calls"
EOF
export PATH="$bin:$PATH" STUB JARVIS_NETWATCH_STATE="$tmp/state" \
  JARVIS_LOG_LIB="$here/../lib/log.sh" JARVIS_LOG_DIR="$tmp/log"
mkdir -p "$tmp/log"

pass=0 fail=0
ok() {
  if "${@:2}"; then pass=$((pass + 1)); else fail=$((fail + 1)) && echo "  FAIL: $1"; fi
}
reset() { rm -rf "$tmp/state" "$STUB"/{calls,gw_ok} && echo wlan0 >"$STUB/wifi"; }
run() { bash "$here/jarvis-netwatch" 2>/dev/null; }
calls() { cat "$STUB/calls" 2>/dev/null || true; }
fails() { cat "$tmp/state/fails"; }
wifi_route() { echo "default via 192.168.1.1 dev wlan0 proto dhcp metric 600" >"$STUB/route"; }

reset && wifi_route && touch "$STUB/gw_ok" && run
ok "healthy: nothing done" test -z "$(calls)"
ok "healthy: counter stays 0" test "$(fails)" == 0

reset && wifi_route && run
ok "one blip: no action yet" test -z "$(calls)"
ok "one blip: counted" test "$(fails)" == 1
run
ok "second failed check: reconnects the Wi-Fi" grep -qx "nmcli device connect wlan0" "$STUB/calls"
run && run
ok "4th failed check: restarts NetworkManager" grep -qx "systemctl restart NetworkManager" "$STUB/calls"
ok "never restarts before the 4th check" test "$(grep -c restart "$STUB/calls")" == 1
touch "$STUB/gw_ok" && run
ok "back: counter reset" test "$(fails)" == 0
ok "back: logged" grep -q "network back" "$tmp"/log/jarvis-system-*.log

reset && : >"$STUB/route" && run && run
ok "no default route at all counts as down" grep -qx "nmcli device connect wlan0" "$STUB/calls"

reset && echo "default via 10.0.0.1 dev eth0" >"$STUB/route" && run && run
ok "default route on Ethernet: nothing to do" test -z "$(calls)"

reset && : >"$STUB/wifi" && run && run
ok "no Wi-Fi device: nothing to do" test -z "$(calls)"

reset && wifi_route && run && run
ok "logs in the Jarvis format under component system" \
  grep -q '\[WARN \] \[system\] \[netwatch\] \[--------\] router unreachable' "$tmp"/log/jarvis-system-*.log

echo "passed: $pass, failed: $fail"
((fail == 0))
