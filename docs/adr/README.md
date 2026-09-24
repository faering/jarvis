# Architecture decisions

One short file per decision: `NNNN-kebab-title.md`. Don't edit a decision once accepted.
To change one, add a new ADR that supersedes it and update the old one's status.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-frontend-stack.md) | Frontend: React/TS in the Tauri webview; native Rust GUI gated on a spike | Accepted |
| [0002](0002-websocket-client-in-webview.md) | The agent WebSocket client lives in TS, not Rust | Accepted |
| [0003](0003-openai-compatible-role-backends.md) | Model roles use OpenAI-compatible HTTP backends | Accepted |
| [0004](0004-independent-component-releases.md) | Independent per-component releases via release-please | Accepted |
| [0005](0005-local-sqlite-state-store.md) | Local SQLite state store with local-first providers | Accepted |

Template:

```markdown
# NNNN. Title
Status: Proposed | Accepted | Superseded by NNNN · Date: YYYY-MM-DD

## Context
## Decision
## Alternatives
## Consequences
## Revisit when
```
