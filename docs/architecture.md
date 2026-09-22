# Architecture

Work routes across three compute layers; the Dockerized agent and the native Tauri display
talk over one WebSocket.

```mermaid
flowchart TB
  subgraph HW["🧩 Raspberry Pi 5 — hardware"]
    direction LR
    CAM["📷 AI Camera<br/>IMX500"]
    HAT["⚡ AI HAT+ 2<br/>Hailo NPU · 40 TOPS"]
    MIC["🎙️ USB mic / speaker"]
    SCR["🖥️ Touchscreen"]
  end
  subgraph DOCKER["🐳 Docker stack · jarvis-net"]
    AGENT["🧠 Agent / API · Python<br/>CPU orchestrator + tools"]
  end
  subgraph APP["🖼️ Tauri app · native, on-device"]
    UI["Frontend · TS/React"]
    RUST["Tauri backend · Rust"]
  end
  CLOUD["☁️ Cloud / larger models"]

  CAM -->|frames| HAT
  HAT -->|features| AGENT
  MIC -->|audio| AGENT
  AGENT <-->|WebSocket| RUST
  RUST --- UI --- SCR
  AGENT -.->|async · heavy tasks| CLOUD

  classDef hw fill:#CCFBF1,stroke:#0D9488,color:#134E4A;
  classDef acc fill:#FFE4E6,stroke:#E11D48,color:#881337;
  classDef agent fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A;
  classDef app fill:#DCFCE7,stroke:#16A34A,color:#14532D;
  classDef cloud fill:#E2E8F0,stroke:#475569,color:#0F172A,stroke-dasharray:4 3;
  class CAM,MIC,SCR hw
  class HAT acc
  class AGENT agent
  class UI,RUST app
  class CLOUD cloud
  style HW fill:#F8FAFC,stroke:#0D9488,color:#134E4A
  style DOCKER fill:#F8FAFC,stroke:#2563EB,color:#1E3A8A
  style APP fill:#F8FAFC,stroke:#16A34A,color:#14532D
```

## Compute layers
1. **IMX500** — on-sensor inference (first pass).
2. **Hailo NPU** — quantized models on-device.
3. **Pi 5 CPU** — orchestrator; always-on voice loop (1–4B). Heavy tasks go **async** to
   cloud/larger models, never on the hot path.

## Boundaries
- **Python** = agent/API + tools (Docker). **TS/React** = frontend. **Rust** = Tauri backend only.
- The display is a **native Tauri app** (not in Docker); it reaches the stack over **WebSocket**.

See [state-machine.md](state-machine.md) for the agent loop, [deploy.md](deploy.md) for delivery.
