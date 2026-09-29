# 0013. The agent decides, the app executes: commands over the WebSocket
Status: Accepted, **an initial approach to revisit** (#223). Date: 2026-09-29.

## Context
Jarvis starts acting on its own body. The first case: minimizing its window to reach the
Pi's desktop, since there is no touchscreen yet (#219). That needs a rule for where
decisions live between the agent (the brain) and the app (the body), the gate, and a way
for the agent to tell the app to act. Until now the protocol only carried conversation
(`say`, `reply`, `state`).

## Decision
- **The agent decides, the app executes.** Only the agent interprets what the user says.
  The app never reads language to pick an action.
- **A `command` message (agent to app)** names one entry from a closed list in the schema
  (`$defs.command`, starting with `window.minimize`). The list is the gate: the app runs only
  names it knows and logs and ignores the rest. So the agent, or anything else that reaches
  the socket, can't make the app do anything outside it, and an older app stays compatible.
- **The app's Rust (Tauri) side performs the action**, the only place that controls the
  window. The UI asks through a Tauri command that AppManifest restricts.
- **Direct local input may do the same without the agent** (Ctrl+M now, touch gestures
  later, #210): it must work when the agent is unreachable, and it's the user acting, not a
  decision about language.
- **Initial approach:** the agent picks commands from fixed phrases matched before the model
  runs ("minimize", "show me the desktop") and replies with a short confirmation. The
  on-device model (1.5B on the CPU; the Hailo NPU isn't in use yet) can't be trusted to call
  tools reliably. Ideally the model decides (#223).

## Alternatives
- **The model decides now (tool calling):** the goal, not yet. A small CPU model would
  sometimes act when not asked, or not act when asked, and every command would wait for
  a model turn.
- **The app matches phrases itself:** rejected. Understanding would be split across two
  components and languages, and would bypass the agent once the model takes over.
- **A generic "do this" message** (script, key presses, shell): rejected. The app would run
  whatever arrives on the socket; a closed list is auditable.
- **A side channel from the agent to Rust** (HTTP, Tauri IPC): rejected. The WebSocket is
  already the one contract (ADR 0008), and the app's TS client owns it (ADR 0002).

## Consequences
- A new command means a schema name, an app handler and an agent trigger. The drift tests on
  both sides enforce the schema part.
- Adding a name isn't breaking: an older app ignores it (Jarvis replies, but nothing
  happens). Release the app first.
- Fixed phrases are brittle: only the listed English wordings work. The matcher is marked in
  the code as temporary, pointing to #223.

## Revisit when
The on-device model (on the NPU, or a bigger local model) calls tools reliably on the command
list, measured by #223's spike, or the list grows beyond a few commands. Then the model picks
commands, and the phrase list goes away or becomes a fast path.
