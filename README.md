# Jarvis

A handheld, physically embodied AI companion — day planning, notes, calendar, and a
sparring partner for hobby projects. Runs on a Raspberry Pi 5 (Hailo NPU + IMX500).

## Roadmap

```mermaid
timeline
  title Jarvis roadmap
  Phase 0 : Dev environment & standards
  Phase 1 : Agent / API + WebSocket + UI shell
  Phase 2 : Always-on voice loop (quantized)
  Phase 3 : On-device inference (Hailo · IMX500 · GPIO)
  Phase 4 : CI/CD — SSH deploy to Pi
  Phase 5 : Self-deploy (human in loop)
```

## Project structure

Four layers: **hardware** (probed) → **backends** (model serving) → **capabilities**
(user-facing abilities, each with a local or remote provider) → **tools** (MCP).

```
agent/                    Python — Jarvis core, the deployable agent
  src/jarvis_agent/
    core/                 loop, state machine, router
    hardware/             device probes + drivers (Pi-only)
    capabilities/         manifests + providers (local | faelab)
    tools/                MCP client + built-in tools
    discovery/            catalogs, mDNS, trust allowlist
    events/               MQTT client, event envelope, notification policy
    store/                local persistent state
frontend/                 Tauri app — TS/React UI + src-tauri/ (Rust)
packages/                 shared TS — protocol (WS + events), ui, config
models/                   model manifest (the store itself is git-ignored)
profiles/                 home.yaml, work.yaml, dev.yaml
deploy/                   compose, systemd units, deploy supervisor
docs/                     architecture, state machine, deployment
scripts/                  ci-local.sh, version.sh
.devcontainer/ .github/ .claude/
```

Jarvis core runs anywhere (Pi, VPS, laptop); what it can do is resolved at startup from
config + probing. Ecosystem tools are discovered over **MCP**; pushed events arrive over
**MQTT**, with Jarvis always connecting outbound.

> Today only `docs/`, `scripts/`, `.devcontainer/`, `.github/` and `.claude/` exist — the
> rest lands with the epics on the [board](https://github.com/users/faering/projects/3).

## Docs
- [Architecture](docs/architecture.md)
- [Agent state machine](docs/state-machine.md)
- [Deployment](docs/deploy.md)
- [GitHub MCP PAT setup](docs/github-mcp-pat.md)
