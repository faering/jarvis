# 0012. A model catalogue, with the model per role chosen per device
Status: Accepted · Date: 2026-09-28

## Context
Jarvis uses several models (LLM, heavy LLM, STT, TTS, and later a VLM, wake word,
embeddings and camera models), and each device can run different ones: the Pi's CPU or
NPU, a mini PC with a GPU, a cloud API. Until #56 the model per role was scattered across
`JARVIS_<ROLE>_MODEL` env vars and compose defaults, there was no vision role, and the
runtime ignored profiles and config files for its backends. Choosing a model also needs
evidence from the device it will run on, not a guess.

## Decision
- **One catalogue, shipped with the agent:** `agent/src/jarvis_agent/models/catalogue.toml`
  lists every model Jarvis knows with its roles, runtime, pinned source and facts (size,
  licence, notes). It changes with the agent version, so a Jarvis release (#162) pins its
  models through the agent.
- **Each device picks one model per role** by catalogue id (`[models]` in its profile or
  config file, or `JARVIS_MODEL_<ROLE>`) and says where each runtime is reached
  (`[runtimes.<name>]`, or `JARVIS_RUNTIME_<NAME>_URL`). The agent builds its backends from
  that; an unknown model, a model in the wrong role or a runtime without an address fails
  startup with every problem listed.
- **Explicit per-field settings still win** (`JARVIS_<ROLE>_BACKEND|_BASE_URL|_MODEL`), so a
  quick experiment needs no catalogue edit.
- **Facts in the catalogue, measurements elsewhere:** benchmark results differ per device
  and over time; they go in dated notes in `docs/experiments/`.
- **Try before deploying:** `python -m jarvis_agent.models` (`list`, `pull`, `chat`,
  `bench`) talks to models directly, on any device, from the agent container.
- **TOML**, like the rest of the agent config (may move to YAML later, with all of it).

## Alternatives
- **Env vars only (as before):** no overview, no validation, and nowhere to record facts
  about a model.
- **YAML (as #56 first proposed):** fine too, but a second config format next to the TOML
  profiles; revisit for all config at once.
- **One catalogue file per device:** repeats each model's facts on every device; the
  split into catalogue (what exists) and assignment (what this device uses) avoids that.
- **Measurements inside the catalogue:** mixes stable facts with per-device, per-date data
  that goes stale.
- **A separate model registry service or artifacts now (the original #56 scope):** built
  NPU/camera models and model artifacts come with #60 / #61, when there's something to build.

## Consequences
- Adding a model = a catalogue entry (with a reason, ideally an experiment note), then an
  assignment in the devices that should use it.
- The runtime now uses the layered config (profile, file, env) for backends and store; an
  invalid config stops the agent instead of being ignored.
- Roles without a backend (`vlm`, `wake_word`, `embed`, `vision`) can already be assigned
  and listed; NPU (`hailo`) and camera (`imx500`) runtimes are refused until wired.

## Revisit when
- Models are built or converted for the NPU/camera (#60, #61), or shipped as artifacts.
- A device needs different models per situation (e.g. on battery), not one per role.
