# 0008. One JSON Schema for the agent↔app WebSocket contract
Status: Accepted · Date: 2026-09-24

## Context
The agent (Python) and the app (TS) release independently (ADR 0004), so their WebSocket
contract must live in one versioned place both sides are checked against (AGENTS.md). Until
#32 each side kept its own copy (`protocol.py`, `frontend/src/agent/protocol.ts`).

## Decision
- **`packages/protocol/protocol.schema.json` (JSON Schema 2020-12) is the source of truth:**
  envelope `v`, one `$defs` entry per message type (payload + examples), routed by `allOf`.
- **Each side hand-writes its code and a test checks it against the schema.** TS lives in
  `@jarvis/protocol` (types + small guards), and its vitest compares the constants, guards and
  examples with the schema. The agent's pytest reads the schema from the repo and compares
  `PROTOCOL_VERSION`, the `Envelope` model and the message types the agent sends or handles.
- **The package ships TS source, with no build step.** Vite, tsc and vitest compile it in the
  app, so `pnpm tauri build` and `pnpm dev` work without running turbo first.
- The app's release manifest reads `PROTOCOL_VERSION` from `packages/protocol/src/index.ts`
  (falling back to `frontend/src/agent/protocol.ts` for older tags). The package's tests keep
  that constant equal to the schema's `v`, so the manifest still reflects the source of truth.

## Alternatives
- **Validator or schema libraries (ajv, zod, pydantic-generated TS):** rejected for now. They
  add runtime dependencies for four messages, and the guards are a few lines each.
- **Codegen (schema → TS/Python):** rejected for now. It needs a generator toolchain on both
  sides, and a drift test gives the same guarantee while the contract is this small.
- **Protobuf/MessagePack:** rejected. JSON over a loopback WebSocket is fast enough, and it
  is easy to debug.
- **Python model as the source (`model_json_schema()`):** rejected. It would put the source
  inside one component, and the schema could not describe payloads per type.

## Consequences
- Adding a message type means changing the schema and both sides in the same PR. Either
  test fails until they match.
- The agent's schema test needs the repo checkout. It does not run inside the agent image.
- A change under `packages/` is outside both release paths, so it bumps neither component.
  A protocol change also touches `frontend/` or `agent/`, and that change triggers the release.

## Revisit when
The number of message types makes hand-written guards error-prone. Codegen or a validator
then becomes worth its dependency.
