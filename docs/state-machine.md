# Agent state machine

The brain: the always-on voice loop. Speech output never blocks — it runs on a
producer/consumer queue and yields at turn boundaries, so a barge-in wins instantly.

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Listening: wake word / touch
  Listening --> Idle: timeout / cancel
  Listening --> Routing: turn boundary (end of utterance)
  Routing --> Speaking: local response (1–4B)
  Routing --> Offloaded: heavy task
  Offloaded --> Idle: dispatched (async)
  Offloaded --> Speaking: result ready (notify)
  Speaking --> Listening: barge-in / expects reply
  Speaking --> Idle: done
```

## States
- **Idle** — always-on wake detection.
- **Listening** — capture the utterance until the turn boundary.
- **Routing** — pick the compute layer: NPU-local vs async cloud/larger model.
- **Speaking** — non-blocking TTS; interruptible.
- **Offloaded** — heavy task runs async; the loop stays responsive; its result re-enters at Speaking.

## Invariants
- Speaking never blocks the loop (producer/consumer queue).
- A barge-in during Speaking jumps straight back to Listening.
