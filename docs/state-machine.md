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

## Implementation
`jarvis_agent.loop.VoiceLoop` runs it: one actor task owns the state; input comes from an
`AudioSource` (mic + wake word + VAD, Pi-only) as `Wake` / `Utterance` / `Cancel`, or as
text. Hot replies stream from the local LLM into speech; heavy ones go to
`Router.offload()` and are spoken once no turn is in progress and the user is not
talking. At most 4 heavy tasks are in flight; past that Jarvis says it is busy. Recent
turns from conversation memory are the LLM context. A `degraded` reply (heavy wanted, local
answered) is spoken as-is and only flagged to the UI.
`runtime.py` builds it all in the FastAPI lifespan (audio out: `NullSink` off-device).

WebSocket (envelope v0, additive): client `say` {text, deep?}; agent `state` {state},
`transcript` {text}, `reply` {delta, done: false, degraded} while streaming, then
`reply` {text, done: true, degraded, spoken?}. `spoken: false` means the speech queue was
full, so the reply was shown but not said. A new client gets `hello`, then the current
`state`.

## Speech output
`jarvis_agent.speech.SpeechQueue` implements Speaking.
- **Producers** call sync `begin_turn`/`feed`/`end_turn`/`say`; they never await TTS.
- **Segmentation:** text is cut at sentence ends (and clauses in long sentences), so TTS
  starts before the reply is complete. The next chunk is synthesized while one plays.
- **Barge-in:** `interrupt()` stops the sink, cancels in-flight TTS and drops all queued
  turns; chunks carry a turn id, so stale audio never plays.
- **Backpressure:** pending text chunks and in-flight turns are both bounded; when full,
  the new chunk or turn is dropped and logged (a dropped turn reports `interrupted`)
  rather than blocking the loop. Audio output is the `AudioSink` seam (Pi speaker later).
