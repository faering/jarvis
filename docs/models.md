# Models: the catalogue and the playground

Which model fills each role (LLM, STT, TTS, vision, …) is config, backed by the model
catalogue, [`catalogue.toml`](../agent/src/jarvis_agent/models/catalogue.toml)
([ADR 0012](adr/0012-model-catalogue.md)).
Try models with the playground before a device uses them; record what you learn in
[`experiments/`](experiments/).

## Pick models for a device
In the device's profile (or a `JARVIS_CONFIG` file):
```toml
[models]
llm = "qwen2.5-1.5b"          # a catalogue id
[runtimes.ollama]
base_url = "http://ollama:11434/v1"
```
Or with env: `JARVIS_MODEL_LLM=qwen2.5-1.5b`, `JARVIS_RUNTIME_OLLAMA_URL=…`. For a quick
try without editing anything, `JARVIS_LLM_MODEL=<runtime name>` overrides just the model.
A new model goes into the catalogue first (roles, runtime, pinned source, facts).

## The playground
`python -m jarvis_agent.models` (in `agent/`: `uv run python -m jarvis_agent.models`; on the
Pi: `docker exec -it jarvis-agent-1 python -m jarvis_agent.models`):

| Command | What it does |
|---|---|
| `list` | the catalogue, and which model fills each role here (and which layer set it) |
| `pull <id>` | download a model into Ollama, with progress |
| `chat <id>` | talk to a model with Jarvis's system prompt; each reply shows time to first token, tokens/s and model load time. `/reset`, `/quit` |
| `bench <id> [<id>…]` | run the prompt set on each model: cold load time, then median time to first token and tokens/s, and memory used. `--markdown` adds every answer side by side, ready for an experiment note |

`--base-url` points at another server, e.g. an Ollama you started by hand next to the
deployment. Ollama models report exact token counts; other runtimes count streamed chunks
(shown as `~`). The prompt set is [`bench_prompts.toml`](../agent/src/jarvis_agent/models/bench_prompts.toml);
`--prompts <file>` uses your own.
