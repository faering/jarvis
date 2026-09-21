---
paths:
  - "frontend/src/**"
  - "frontend/*.{ts,tsx,js,jsx,json,html,css}"
---

# Frontend (TS/React) rules

- This is the **frontend** — TypeScript/React only. **No agent logic** and **no Rust** here;
  the Rust Tauri backend lives in `frontend/src-tauri/` (see its own rules).
- Format with **prettier**, lint with **eslint** (both run in pre-commit).
- The UI talks to the agent stack **only over the WebSocket bridge** — no direct DB/tool
  access. Handle reconnection and surface connection state.
- Touch-first: design for the 4–5" touchscreen (day planning, notes, calendar).
- Keep components typed; avoid `any`. Prefer semantic, accessible markup.
