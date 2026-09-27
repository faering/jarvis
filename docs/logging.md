# Logging

One log format and one set of levels for every Jarvis component (agent, app, deploy
scripts) and for Faelab to adopt. Plain text for people; every field maps to the
[OpenTelemetry log data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/),
so a collector can ingest the files later. Decision: [ADR 0011](adr/0011-log-format-and-levels.md).

## Line format

```
[<timestamp>] [<LEVEL>] [<component>] [<logger>] [<turn>] <message>  <key>=<value> ...
```

| Slot | Content | OTel field |
|------|---------|------------|
| timestamp | UTC, millisecond precision: `2026-09-27 15:44:38.123Z` | `Timestamp` |
| LEVEL | `TRACE` `DEBUG` `INFO ` `WARN ` `ERROR` `FATAL`, padded to 5 | `SeverityText` (+ `SeverityNumber`) |
| component | `agent`, `app`, `deploy`, … (Faelab: its own names) | resource `service.name` |
| logger | where in the code, dotted: `voice.stt`, `speech.tts`, `presence` | instrumentation scope name |
| turn | first 8 hex chars of the trace id, or `--------` | `TraceId` |
| message | one line, human-readable; newlines escaped as `\n` | `Body` |
| attributes | two spaces, then `key=value` pairs | `Attributes` |

- **Attribute keys** are `snake_case`, dotted for OTel semantic conventions (`error.type`,
  `http.route`). Values containing a space, `=` or `"` are double-quoted with `\"` and `\\`
  escaped.
- **ERROR and FATAL** add indented continuation lines (4 spaces): `at <file>:<line> in
  <function>`, then the stack trace. A line that doesn't start with `[` belongs to the record
  above it.
- **The full trace id** (32 hex, W3C) is logged once, as `trace_id=` on the line that starts
  a turn or request; every later line of that turn carries its 8-char prefix.
- **A header line** is written whenever a process opens its file:
  `... [INFO ] [agent] [log] [--------] log opened  service.version=0.2.0 pid=1`.

### Examples

[`logging-examples.log`](logging-examples.log) is the shared test fixture: every writer's
formatter and the `jarvis-logs` parser are tested against it. Extend it with any new edge case.

```
[2026-09-27 15:44:38.101Z] [INFO ] [agent] [voice.loop] [4bf92f35] turn started  trace_id=4bf92f3577b34da6a3ce929d0e0e4736 source=wake_word
[2026-09-27 15:44:38.435Z] [DEBUG] [agent] [voice.stt] [4bf92f35] transcribed  duration_ms=312 chars=27
[2026-09-27 15:44:39.301Z] [WARN ] [agent] [routing] [4bf92f35] slow first token, falling back  backend=local latency_ms=2100
[2026-09-27 15:44:39.310Z] [INFO ] [app] [presence] [4bf92f35] state changed  state=thinking
[2026-09-27 15:44:40.002Z] [ERROR] [agent] [speech.tts] [4bf92f35] synthesis failed  error.type=TimeoutError
    at jarvis_agent/speech/tts.py:88 in synthesize
    Traceback (most recent call last): ...
[2026-09-27 16:02:11.740Z] [WARN ] [deploy] [rollback] [--------] health check failed, rolling back  attempt=2
```

## Levels

Following [dash0: log levels](https://www.dash0.com/knowledge/log-levels) and the OTel
severity numbers. On a single-user device, "action" means what Jarvis does.

| Level | When to use | Action | SeverityNumber |
|-------|-------------|--------|----------------|
| TRACE | Granular execution flow (loop steps, large payloads) | None | 1 |
| DEBUG | Diagnostic state for specific contexts | None | 5 |
| INFO | A standard business or operational event occurred | None | 9 |
| WARN | Functioning, but with degradation risk | Daily summary; Jarvis offers to file an issue | 13 |
| ERROR | A request or operation failed; the app still runs | Jarvis tells you on spikes/trends | 17 |
| FATAL | Cannot start, or must terminate immediately | Alert immediately, from outside the dying process (#65) | 21 |

Per runtime:

| Runtime | TRACE | DEBUG | INFO | WARN | ERROR | FATAL |
|---------|-------|-------|------|------|-------|-------|
| Python `logging` | custom level 5 | `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` |
| TS (app) | `trace` | `debug` | `info` | `warn` | `error` | `fatal` (logs, then exits) |
| Rust `log` | `trace!` | `debug!` | `info!` | `warn!` | `error!` | `error!` + exit, text `FATAL` |
| bash | `log TRACE` | `log DEBUG` | `log INFO` | `log WARN` | `log ERROR` | `log FATAL` + `exit` |

The text is always the OTel name (`WARN`, `FATAL`), never `WARNING` or `CRITICAL`.

- **Defaults:** INFO in production, DEBUG in dev; levels are set per logger in config
  (ADR 0007). TRACE is never on by default.
- **Never logged:** secrets, tokens, API keys, auth headers, user audio. User text (what
  you said, what Jarvis replied) appears only at TRACE.

## Files and budget

- **Where:** `/var/log/jarvis/jarvis-<component>-YYYY-MM-DD.log` on the Pi, one file per
  component per UTC day (`logs/` in the repo in dev, git-ignored). Each component also
  writes the same lines to stderr, so crashes before logging starts still reach the journal.
- **Access:** the folder is `root:jarvis-log`, mode `2775`; files are `0640`. The agent
  container (`group_add` of the group's fixed GID **2750**), the app's user (your login, which
  runs the display) and the root deploy scripts write there; the `deploy` SSH user does not.
  `scripts/pi/setup.sh` creates the group and folder; the app gets `JARVIS_LOG_DIR` from
  `/etc/environment.d/60-jarvis-logs.conf`.
- **Bash:** scripts log through `scripts/lib/log.sh` (installed root-owned to
  `/usr/local/lib/jarvis/log.sh`): `log WARN rollback "health check failed" attempt=2`.
  Root scripts source it only when root owns it, and it never writes through a symlink.
- **Retention:** 90 days.
- **Budget:** 20 GiB for the folder; 500 MiB per component per day. Set generously on the
  256 GB card so nothing useful is dropped; revisit once `jarvis-logs usage` shows real
  daily and monthly volumes. At the daily cap a
  writer keeps only WARN and above and logs one ERROR saying so; at 110% it stops writing
  until the next day.
- **Pruning:** `jarvis-logs prune` (hourly `jarvis-logs-prune.timer`, as a throwaway user
  with only the log group) deletes files older than 90 days, then the oldest files until the
  folder is under budget. It touches only `jarvis-*-YYYY-MM-DD.log` files and never today's
  (they're open, so deleting frees nothing). `--dry-run` shows what it would delete.
- **Watcher:** the agent checks the folder every minute. At **80%** of the folder budget,
  or of a component's daily cap, it logs a WARN and Jarvis tells you; it alerts again only
  after usage has dropped below 70%.

## Reading logs

`jarvis-logs` merges every component's files into one timeline (continuation lines stay
with their record) and filters them:

```bash
jarvis-logs --since 1h                      # everything from the last hour
jarvis-logs --turn 4bf92f35                 # one turn, across agent and app
jarvis-logs --level WARN --component agent  # WARN and above from the agent
jarvis-logs -f                              # last 10 records, then follow, like tail -f
jarvis-logs usage                           # size per component per day and month, vs budget
```

`--since` takes `30m`, `1h`, `2d` or an ISO time (UTC unless it has an offset); `--turn`
takes the 8-char id or the full trace id; `-n N` keeps the last N records; `--dir` defaults
to `$JARVIS_LOG_DIR`, else `/var/log/jarvis`.
