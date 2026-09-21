---
paths:
  - "frontend/src-tauri/**"
---

# Tauri backend (Rust) rules

- Rust is allowed **only here** — the Tauri backend. **Never put agent logic in Rust**; it
  belongs in the Python agent layer.
- Keep this a **thin native bridge**: window/app lifecycle, OS integration, and forwarding
  between the UI and the agent stack's WebSocket. No business logic.
- Format with **cargo fmt**, lint with **cargo clippy** (`-D warnings`); both run in
  pre-commit.
- The Tauri app runs **natively on-device, not in Docker**.
