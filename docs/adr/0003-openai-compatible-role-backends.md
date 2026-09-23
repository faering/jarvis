# 0003. OpenAI-compatible role backends
Status: Accepted · Date: 2026-09-23

## Context
The agent needs LLM, STT and TTS (and later Vision). The same agent code has to run in the
devcontainer (CPU) and on the Pi (Hailo NPU) with no code changes (#58, #57).

## Decision
- **One async interface per role.** Every real backend is an **OpenAI-compatible HTTP**
  client, and a mock backend covers tests and CI. The backend, base URL and model come from
  env config.
- **Dev serving stack:**
  - **ollama** for the LLM, running `qwen2.5:1.5b`. The same model is in the Hailo-10H
    model zoo, so dev and Pi use one model.
  - **speaches** for STT and TTS (faster-whisper and Piper voices), in one service.
- **Pi:** Hailo-Ollama for the LLM. It speaks Ollama's API, and whether it also serves the
  OpenAI `/v1` endpoints is unverified. If it doesn't, we add an Ollama-native adapter
  behind the same interface.

## Alternatives
- **whisper.cpp and piper as separate services:** rejected for dev.
  - Piper has no OpenAI-style API, so it would need a custom client.
  - whisper.cpp can serve `/v1/audio/transcriptions`, but that's two services instead of one.
- **The official `openai` SDK:** rejected, because `httpx` covers the three endpoints with no
  extra dependency.
- **A native client per backend:** rejected, because it means more code and a code change
  to switch between dev and Pi.

## Consequences
- Switching dev↔Pi is a config change.
- The speaches image is pinned to a release candidate for now.
- Vision stays a mock until the IMX500 and Hailo pipelines exist (#35, #60).
- Routing policy (#25) and the config schema (#73) build on these interfaces.

## Revisit when
Hailo-Ollama turns out not to serve the OpenAI API, speaches stalls or breaks, or
latency on the hot path calls for a streaming protocol that the OpenAI API can't provide.
