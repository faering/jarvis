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

## Docs
- [Architecture](docs/architecture.md)
- [Agent state machine](docs/state-machine.md)
- [Deployment](docs/deploy.md)
- [GitHub MCP PAT setup](docs/github-mcp-pat.md)
