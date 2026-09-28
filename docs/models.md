# Models

Every model Jarvis knows is in [`catalogue.toml`](../agent/src/jarvis_agent/models/catalogue.toml)
([ADR 0012](adr/0012-model-catalogue.md)). A device picks one per role; the playground
tries models first. Results go in [`experiments/`](experiments/).

## Playground on the Pi
Needs agent ≥ 0.4.0 for `ollama:<name>` (check: `curl -s 127.0.0.1:8000/version`).
```sh
# a lab Ollama next to the deployment; its models survive in the volume
docker run -d --name ollama-lab --network jarvis-net -v ollama-lab:/root/.ollama ollama/ollama:0.34.3
docker start ollama-lab          # after a reboot (it doesn't restart by itself)
docker rm -f ollama-lab          # when done (models stay in the ollama-lab volume)

# shorthand for this shell
m() { docker exec -it jarvis-agent-1 python -m jarvis_agent.models "$@"; }
LAB="--base-url http://ollama-lab:11434/v1"

m list                                   # the catalogue, and this device's model per role
m pull ollama:gemma3:1b $LAB             # download (any Ollama model: ollama:<name>)
m chat ollama:gemma3:1b $LAB             # talk to it; /reset, /quit
m bench ollama:gemma3:1b ollama:llama3.2:3b $LAB                                  # compare
docker exec jarvis-agent-1 python -m jarvis_agent.models bench \
  ollama:gemma3:1b ollama:llama3.2:3b --base-url http://ollama-lab:11434/v1 --markdown > bench.md
```
In dev: `cd agent`, `docker compose up -d ollama`, then
`JARVIS_RUNTIME_OLLAMA_URL=http://ollama:11434/v1 uv run python -m jarvis_agent.models …`.

## Reading `bench`
| Column | Meaning |
|---|---|
| LOAD s | cold model load (bench unloads first; `--warm` skips that) |
| FIRST TOKEN s | median time to the first word |
| TOK/S | median generation speed (`~` = approximate, non-Ollama) |
| IN MEMORY | size loaded |
| CPU °C | before → after; around 80 °C the Pi throttles |

Thinking models answer without thinking unless `--think`. `--markdown` adds every answer.
Prompts: [`bench_prompts.toml`](../agent/src/jarvis_agent/models/bench_prompts.toml) (or `--prompts file.toml`).

## Use a model on a device
Add it to the catalogue, then in the device profile:
```toml
[models]
llm = "qwen2.5-1.5b"
[runtimes.ollama]
base_url = "http://ollama:11434/v1"
```
Or env: `JARVIS_MODEL_LLM=<id>`, `JARVIS_RUNTIME_OLLAMA_URL=<url>`.
