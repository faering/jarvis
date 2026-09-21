---
name: plan-issue
description: Read a GitHub issue, check it against the architecture decisions in AGENTS.md, and produce an implementation plan — posted as an issue comment and shown in chat. Use before implementing a work item.
---

# plan-issue [issue-number]

Turns an issue into a checked, actionable plan. MCP-first.

## Steps
1. **Read the issue** (`issue_read`, or the local mirror) — title, summary, acceptance
   criteria, and the architecture decisions it touches.
2. **Check against AGENTS.md** — language boundaries, three-compute-layer routing, the
   Docker/Tauri split, CI/CD + release/commit conventions, and Pi-only constraints. Flag any
   conflict or boundary the work would cross.
3. **Produce the plan** — approach, the files/components to touch, tests/verification, and
   how it satisfies each acceptance criterion. Keep it concise; reuse existing code.
4. **Post it** as an issue comment (`add_issue_comment`) and show it in chat.

## Notes
- If the issue is ambiguous or under-specified, ask before planning — don't assume intent.
- For a dependency's API/config, pull current docs first (`docs-lookup`).
- This plans; it does not implement. Begin the work with `start-issue`.
