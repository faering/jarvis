# 0002. Agent WebSocket client lives in the webview (TS)
Status: Accepted · Date: 2026-09-23

## Context
The Tauri app needs a connection to the agent's WebSocket (v0 envelope, #30). It could
live in the TS frontend or in the Rust backend, forwarding to the UI over IPC.

## Decision
- **The client is TS, in the webview. Rust does not proxy it.**
- **Handshake:** a `hello` handshake checks the protocol version. On a mismatch the client
  stops reconnecting and shows "incompatible" with a manual retry, because retrying cannot
  fix a version mismatch.
- **Liveness:** a ping/pong heartbeat detects half-open connections, and reconnects use
  jittered exponential backoff up to 10 s.
- **Agent URL:** set at build time (`VITE_AGENT_WS_URL`), and it must also be listed in the
  CSP `connect-src`.

## Alternatives
- **Rust WebSocket plus IPC to the UI:** rejected for now.
  - It adds an IPC hop and Rust state, and it's harder to test.
  - Its advantages don't apply to a plaintext loopback connection: TLS and cert pinning,
    keeping the connection across webview reloads, and bypassing the CSP.
- **Runtime-configurable agent URL:** deferred to the Pi deploy (#37).

## Consequences
- The client is testable in plain Node against a fake server.
- `src-tauri` stays a thin shell.
- The earlier notes that describe Rust as the WebSocket bridge (`.claude/rules/tauri.md` and
  the `AGENT <-> RUST` edge in `docs/architecture.md`) are corrected by the #30 PR, which
  implements this decision.

## Revisit when
The connection needs TLS or pinning, must outlive webview reloads, or the UI moves to a
native Rust GUI (ADR 0001). The client sits behind one interface, so it can move.
