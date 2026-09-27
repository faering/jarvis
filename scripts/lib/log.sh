# shellcheck shell=bash
# Shared bash logger for Jarvis scripts, in the docs/logging.md line format. The Pi setup
# installs it root-owned as /usr/local/lib/jarvis/log.sh; scripts source it only when root
# owns it and nobody else can write it.
#
#   log LEVEL LOGGER MESSAGE [key=value ...]     e.g.  log WARN rollback "health check failed" attempt=2
#
# Writes the line to stderr and appends it to $JARVIS_LOG_DIR/jarvis-<component>-<UTC date>.log
# (0640; the folder's setgid group makes it jarvis-log). Logging never fails the caller: no
# folder, no permission or no python3 just means stderr only. FATAL doesn't exit; the caller does.
# Env: JARVIS_LOG_DIR (default /var/log/jarvis), JARVIS_LOG_COMPONENT (default deploy),
#      JARVIS_LOG_TURN (8 hex chars, default --------).

_jarvis_log_value() { # quote a value per the spec: "..." when it has a space, =, " or is empty
  local v="$1"
  if [[ -z "$v" || "$v" == *[[:space:]=\"]* ]]; then
    v="${v//\\/\\\\}"
    v="${v//\"/\\\"}"
    v="${v//$'\n'/\\n}"
    v="${v//$'\r'/\\r}"
    v="${v//$'\t'/\\t}"
    v="\"$v\""
  fi
  printf '%s' "$v"
}

log() { # log LEVEL LOGGER MESSAGE [key=value ...]
  local level="${1:-INFO}" logger="${2:-main}" msg="${3:-}" comp turn dir ts line kv
  shift 3 2>/dev/null || shift $#
  case "$level" in TRACE | DEBUG | INFO | WARN | ERROR | FATAL) ;; *) level=INFO ;; esac
  comp="${JARVIS_LOG_COMPONENT:-deploy}"
  [[ "$comp" =~ ^[a-z0-9][a-z0-9_.-]*$ ]] || comp=deploy
  turn="${JARVIS_LOG_TURN:---------}"
  [[ "$turn" =~ ^[0-9a-f]{8}$ ]] || turn=--------
  msg="${msg//$'\r'/\\r}"
  msg="${msg//$'\n'/\\n}"
  ts="$(date -u '+%Y-%m-%d %H:%M:%S.%3NZ')"
  printf -v line '[%s] [%-5s] [%s] [%s] [%s] %s' "$ts" "$level" "$comp" "$logger" "$turn" "$msg"
  if (($#)); then
    line+=" "
    for kv; do
      [[ "$kv" == *=* ]] || kv="arg=$kv"
      line+=" ${kv%%=*}=$(_jarvis_log_value "${kv#*=}")"
    done
  fi
  printf '%s\n' "$line" >&2
  dir="${JARVIS_LOG_DIR:-/var/log/jarvis}"
  [[ -d "$dir" && ! -L "$dir" ]] || return 0
  # Append without following a symlink or blocking on a FIFO: the folder is group-writable,
  # so a jarvis-log member must not be able to point root's write at another file.
  python3 -c '
import os, stat, sys
os.umask(0o027)
flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
fd = os.open(sys.argv[1], flags, 0o640)
try:
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        sys.exit(1)
    os.write(fd, (sys.argv[2] + "\n").encode())
finally:
    os.close(fd)
' "$dir/jarvis-$comp-${ts%% *}.log" "$line" 2>/dev/null || true
  return 0
}
