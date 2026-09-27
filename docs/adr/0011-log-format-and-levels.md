# 0011. Plain-text logs on the Pi, OpenTelemetry-shaped, one set of levels
Status: Accepted · Date: 2026-09-27

## Context
Logging so far is ad hoc (Python defaults, Docker's log driver). Before real logging lands
in the agent, the app and the deploy scripts, they need one format that people can read on
the Pi and that Jarvis can search (#127), with turn correlation across agent and app, and
bounded disk use on an SD card. Faelab has no log collector yet.

## Decision
The full spec is [docs/logging.md](../logging.md). In short:
- **Plain text, one record per line**, fixed slots:
  `[timestamp] [LEVEL] [component] [logger] [turn] message  key=value ...`. Every slot maps
  to an OpenTelemetry log field, so one regex turns a line back into an OTel record.
- **UTC timestamps with `Z`**, millisecond precision, first in the line, so lines from
  different files sort into one timeline.
- **Levels** per dash0 with OTel severity numbers: TRACE, DEBUG, INFO, WARN, ERROR, FATAL,
  with a defined action for each on a single-user device.
- **Logs stay on the Pi:** `/var/log/jarvis/jarvis-<component>-YYYY-MM-DD.log`, one file
  per component per UTC day; `jarvis-logs` merges them for reading.
- **Correlation:** a W3C trace id per voice turn or request, created by the agent and sent
  to the app over the WebSocket; lines show its 8-char prefix.
- **Budget:** 30 days, 1 GiB for the folder, 50 MiB per component per day; hourly pruning;
  the agent alerts you at 80%.
- **Libraries:** Python's standard `logging` (no structlog), the Tauri log plugin for the
  app, a shared `log` function for bash.

## Alternatives
- **JSON Lines:** machine-first and trivially OTel-mappable, but hard to read on the Pi;
  the fixed-slot text keeps the mapping without that cost.
- **journald as the store:** already set up and bounded, but Docker stores each line as an
  unstructured message, traces don't fit, and the native app needs its own route in.
- **One shared file for all components:** a single timeline without merging, but two
  writers (container and native app) interleave and clash on rotation.
- **OpenTelemetry SDK + collector now:** full fidelity, but a collector and backend cost
  memory on the Pi and there's nowhere to send data until Faelab has one.
- **Elastic Common Schema:** Elastic-specific and being merged into OTel semantic
  conventions.
- **structlog:** nicer API, but a plain-text format doesn't need it; revisit if context
  handling in `logging` gets awkward.

## Consequences
- Every component formats the same line; a shared test fixture of example lines checks
  each writer and the `jarvis-logs` parser.
- The WebSocket protocol gets an optional `trace_id` on agent messages (#126).
- Pi setup creates the log folder, group and prune timer; the agent container mounts the
  folder.
- The full trace id appears once per turn, so later OTel export keeps exact correlation.

## Revisit when
- Faelab runs a collector: add an OTLP exporter (or a collector reading these files).
- Disk or SD wear becomes a problem, or the budget alerts fire regularly.
