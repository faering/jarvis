---
paths:
  - "frontend/src-tauri/**"
---

# Tauri backend (Rust) rules

- Rust is allowed **only here** — the Tauri backend. **Never put agent logic in Rust**; it
  belongs in the Python agent layer.
- Keep this a **thin native bridge**: window/app lifecycle and OS integration. No business
  logic. The WebSocket client lives in TS; Rust does not proxy it.
- Format with **cargo fmt**, lint with **cargo clippy** (`-D warnings`); both run in
  pre-commit.
- The Tauri app runs **natively on-device, not in Docker**.
