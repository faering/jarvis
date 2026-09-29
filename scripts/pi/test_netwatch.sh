#!/usr/bin/env bash
# Tests for scripts/pi/jarvis-netwatch with nmcli, ip, ping, systemctl and modprobe stubbed,
# a fake /sys/class/net and /proc/modules, and 1 s step deadlines.
# Usage: scripts/pi/test_netwatch.sh   (exits non-zero on any failure)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
bin="$tmp/bin" STUB="$tmp/stub"
mkdir -p "$bin" "$STUB"
stub() { cat >"$bin/$1" && chmod +x "$bin/$1"; }
# Scenario knobs in $STUB: route, gw_ok (ping answers), fix_at_<step> (that step brings the
# network back), hang_<cmd> (that command never returns), fail_<cmd> (it exits 1).
stub nmcli <<'EOF'
#!/usr/bin/env bash
echo "nmcli $*" >>"$STUB/calls"
[[ ! -e "$STUB/hang_nmcli" ]] || exec sleep 30
[[ ! -e "$STUB/fail_nmcli" ]] || exit 1
[[ ! -e "$STUB/fix_at_reconnect" ]] || touch "$STUB/gw_ok"
EOF
stub systemctl <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$STUB/calls"
[[ "$1" != restart || ! -e "$STUB/hang_systemctl" ]] || exec sleep 30
[[ "$1" != restart || ! -e "$STUB/fix_at_restart" ]] || touch "$STUB/gw_ok"
EOF
stub modprobe <<'EOF'
#!/usr/bin/env bash
echo "modprobe $*" >>"$STUB/calls"
[[ ! -e "$STUB/hang_modprobe" ]] || exec sleep 30
[[ "$1" == -r || ! -e "$STUB/fix_at_driver" ]] || touch "$STUB/gw_ok"
EOF
stub ip <<'EOF'
#!/usr/bin/env bash
cat "$STUB/route" 2>/dev/null
EOF
stub ping <<'EOF'
#!/usr/bin/env bash
[[ -e "$STUB/gw_ok" ]]
EOF
export PATH="$bin:$PATH" STUB JARVIS_NETWATCH_STATE="$tmp/state" JARVIS_NETWATCH_KEEP="$tmp/keep" \
  JARVIS_NETWATCH_SYS_NET="$tmp/sys" JARVIS_NETWATCH_MODULES="$tmp/modules" JARVIS_NETWATCH_STEP_S=1 \
  JARVIS_LOG_LIB="$here/../lib/log.sh" JARVIS_LOG_DIR="$tmp/log"

pass=0 fail=0
ok() {
  if "${@:2}"; then pass=$((pass + 1)); else fail=$((fail + 1)) && echo "  FAIL: $1"; fi
}
reset() {
  rm -rf "$tmp/state" "$tmp/keep" "$tmp/sys" "$tmp/log" "${STUB:?}"/*
  mkdir -p "$tmp/sys/wlan0/wireless" "$tmp/sys/eth0" "$tmp/log"
  printf 'brcmfmac 1 1 brcmfmac_wcc, Live\nbrcmfmac_wcc 1 0 - Live\nbrcmutil 1 1 brcmfmac, Live\n' >"$tmp/modules"
  echo "default via 192.168.1.1 dev wlan0 proto dhcp metric 600" >"$STUB/route"
}
run() { bash "$here/jarvis-netwatch" 2>/dev/null; }
runs() { for ((n = 0; n < $1; n++)); do run; done; }
calls() { cat "$STUB/calls" 2>/dev/null || true; }
state() { cat "$tmp/state/state"; }
logs() { cat "$tmp"/log/jarvis-system-*.log 2>/dev/null || true; }

reset && touch "$STUB/gw_ok" && run
ok "healthy: nothing done" test -z "$(calls)"
ok "healthy: nothing logged" test -z "$(logs)"

reset && run
ok "check 1: a blip, no action" test -z "$(calls)"
ok "check 1: counted" test "$(state)" == "1 none"
run
ok "check 2: reconnects the Wi-Fi" grep -qx "nmcli --wait 1 device connect wlan0" "$STUB/calls"
run
ok "check 3: restarts NetworkManager" grep -qx "systemctl restart NetworkManager" "$STUB/calls"
run
ok "check 4: unloads the vendor module first" grep -qx "modprobe -r brcmfmac_wcc brcmfmac" "$STUB/calls"
ok "check 4: loads the driver again" grep -qx "modprobe brcmfmac" "$STUB/calls"
ok "one step per check, each once" test "$(calls | grep -vc reboot)" == 4
ok "no reboot before check 5" bash -c "! grep -q reboot '$STUB/calls'"
run
ok "check 5: reboots" grep -qx "systemctl reboot" "$STUB/calls"
ok "check 5: reboot logged with its reason" bash -c "grep -q 'rebooting: no network after 4 steps' <<<'$(logs)'"
ok "check 5: reboot time kept across reboots" test -s "$tmp/keep/last-reboot"

reset && touch "$STUB/fix_at_restart" && runs 4
ok "recovery names the step that fixed it" \
  bash -c "grep -q 'network back .*after_failed_checks=3 fixed_by=restart-networkmanager' <<<'$(logs)'"
ok "recovery resets the ladder" test "$(state)" == "0 none"

reset && touch "$STUB/fix_at_driver" && runs 5
ok "driver reload fixes it: no reboot" bash -c "! grep -q reboot '$STUB/calls'"
ok "driver reload fixes it: logged" bash -c "grep -q 'fixed_by=reload-driver' <<<'$(logs)'"

reset && touch "$STUB/fail_nmcli" && runs 2
ok "a failed step is logged and the ladder goes on" bash -c "grep -q 'reconnect failed' <<<'$(logs)'"

reset && touch "$STUB/hang_nmcli" && start=$SECONDS && runs 2
ok "a hung step is abandoned at the deadline" test $((SECONDS - start)) -lt 5
ok "a hung step reboots at once, forced" grep -qx "systemctl reboot --force" "$STUB/calls"
ok "a hung step is logged" bash -c "grep -q 'reconnect hung' <<<'$(logs)'"

reset && touch "$STUB/hang_modprobe" && runs 4
ok "a hung driver reload reboots, forced" grep -qx "systemctl reboot --force" "$STUB/calls"

reset && mkdir -p "$tmp/keep" && date +%s >"$tmp/keep/last-reboot" && runs 5
ok "rate limit: no second reboot within the hour" bash -c "! grep -q reboot '$STUB/calls'"
ok "rate limit: logged" bash -c "grep -q 'reboot skipped' <<<'$(logs)'"
ok "rate limit: the ladder starts over" test "$(state)" == "1 reboot-skipped"
: >"$STUB/calls" && run
ok "rate limit: next check reconnects again" grep -qx "nmcli --wait 1 device connect wlan0" "$STUB/calls"

reset && mkdir -p "$tmp/keep" && echo $(($(date +%s) - 3601)) >"$tmp/keep/last-reboot" && runs 5
ok "an hour later it may reboot again" grep -qx "systemctl reboot" "$STUB/calls"

reset && : >"$STUB/route" && runs 2
ok "no default route counts as down" grep -q "device connect wlan0" "$STUB/calls"

reset && echo "default via 10.0.0.1 dev eth0" >"$STUB/route" && runs 5
ok "default route on Ethernet: nothing to do" test -z "$(calls)"

reset && rm -rf "$tmp/sys/wlan0" && runs 5
ok "no Wi-Fi device: nothing to do" test -z "$(calls)"

reset && runs 1
ok "logs in the Jarvis format under component system" \
  bash -c "grep -q '\[WARN \] \[system\] \[netwatch\] \[--------\] router unreachable' <<<'$(logs)'"

echo "passed: $pass, failed: $fail"
((fail == 0))
