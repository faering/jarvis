@AGENTS.md
@CONTEXT.md

# Claude Code specifics

The canonical instructions are in AGENTS.md (imported above); the Jarvis domain glossary is
in CONTEXT.md. Only Claude-Code-specific notes belong here.

- **Skills** live in `.claude/skills/`: `docs-lookup` (pull current docs via context7 before
  answering library/API questions), `new-issue`, `plan-issue`, `open-pr`, `wi-fetch`,
  `wi-push`, `wi-sync`. The shared issue schema is `.claude/skills/_shared/issue-schema.md`.
- **Path-scoped rules** in `.claude/rules/` load automatically when you touch matching files
  (e.g. `agent/**`, `frontend/**`, `frontend/src-tauri/**`) — don't restate them here.
- **Plan mode** for large or multi-file changes; confirm the approach before writing.
