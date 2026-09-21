# Domain language

The ubiquitous vocabulary of Jarvis. Use these terms precisely in code, issues, and docs.

## Product & hardware
- **Jarvis** — a handheld, physically embodied AI companion (Pi-based) for day planning,
  notes, calendar, and hobby-project sparring.
- **Orchestrator** — the Raspberry Pi 5 CPU; coordinates I/O and routes work across compute
  layers.
- **AI HAT+ 2 / Hailo NPU** — the Hailo-10H neural accelerator (40 TOPS, 8GB) for on-device
  model inference.
- **AI Camera / IMX500** — Raspberry Pi AI Camera with on-sensor inference; the first
  compute layer.
- **Enclosure** — the 3D-printed body housing the Pi, HAT, camera, mic/speaker, and screen.

## Compute & routing
- **Three-compute-layer routing** — dispatch across IMX500 (on-camera) → Hailo NPU → Pi 5
  CPU orchestrator, escalating as needed.
- **Hot path** — the latency-critical always-on interaction loop; must stay non-blocking.
- **Always-on voice loop** — the continuous listen/respond loop driven by small quantized
  models.
- **Quantized model (1–4B)** — a small local model used on the hot path.
- **Async route** — offloading heavy tasks to the cloud or larger local models, off the hot
  path.

## Voice & interaction
- **Turn boundary** — the point where one speaker's turn ends and another begins; gates
  speech segmentation and interruption.
- **Producer/consumer speech queue** — the async queue that decouples speech generation from
  playback so output never blocks the loop.

## Software architecture
- **Agent / API layer** — the Python service(s) implementing agent logic and tools; runs in
  the Docker stack.
- **Tool** — a Python capability the agent can invoke (calendar, notes, etc.).
- **Agent stack / Docker stack** — the Docker Compose services (agent + tools).
- **Tauri app** — the native display app (TS/React UI + Rust backend); runs on-device, not
  in Docker.
- **Tauri backend** — the Rust side of the Tauri app; the only place Rust is allowed.
- **jarvis-net** — the external Docker network shared by the compose stack and the
  devcontainer.
- **WebSocket bridge** — the connection between the native Tauri app and the agent stack.

## Delivery
- **Devcontainer** — the reproducible dev environment (Python/Node/Rust/Tauri); excludes the
  Pi-only inference path.
- **Self-deploy** — the stretch goal where Jarvis detects a new release and deploys itself
  with human approval.

## Work items
- **Work item (WI)** — a unit of tracked work: Epic → Feature → Story → Task, or a Bug.
- **Epic / Feature / Story / Task / Bug** — the Agile hierarchy; modeled via `type:*` labels.
- **Parent** — the work item one level up; how hierarchy is recorded (labels can't nest).
- **Local mirror** — `github-issues.json`, the local copy of GitHub work items.
- **baseSnapshot** — an item's last-synced content, used as the base for 3-way merge.
- **3-way merge / conflict resolution** — reconciling local vs. remote against baseSnapshot;
  genuine conflicts resolved per-item (GitHub-wins / JSON-wins).
- **wi-fetch / wi-push / wi-sync** — the skills that pull, push, and reconcile work items.
