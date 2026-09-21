---
paths:
  - "agent/**/*.py"
---

# Python agent rules

- This is the **agent/API layer and tools** — Python only. No TS or Rust logic here.
- Format/lint with **ruff** (`ruff format`, `ruff check`); it runs in pre-commit.
- Use full **type hints** and prefer explicit, small functions.
- I/O and the interaction loop are **async**; never block the hot path — heavy work goes to
  an async route (cloud / larger local model), and speech output goes through the
  producer/consumer queue with turn-boundary checks.
- The **three-compute-layer routing** is behind an interface with pluggable backends; the
  CPU-orchestrator path must work off-device (mock NPU/camera) so it runs in the
  devcontainer and CI.
- Tests are **pytest**, run on the `pre-push` stage. Keep hardware (Hailo/IMX500/GPIO)
  behind mockable seams — the real path is Pi-only.
- Expose the display contract over **WebSocket**; the Tauri app is the client.
