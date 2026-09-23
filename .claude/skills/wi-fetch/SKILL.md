---
name: wi-fetch
description: Pull all GitHub issues into the local mirror github-issues.json (GitHub is source of truth). Use to refresh the local backlog cache before reading or editing work items, or as the read half of wi-sync.
---

# wi-fetch

Refreshes the **git-ignored** local mirror from GitHub. GitHub is the source of truth; the
mirror is a fast local cache. Work-item shape + fields: `_shared/issue-schema.md`.
MCP-first (`mcp__github__*`).

## Steps
1. **List issues** — `list_issues` (state `all`, paginate 5–10) or `search_issues`. For each
   read number, node_id, title, body, labels, assignees, state, updated_at, url, and the
   sub-issue parent if present.
2. **Map each to a WorkItem:**
   - `type` ← `type:*` label; `priority` ← `prio:*`; `status` ← `status:*`.
   - `title`, `summary`, `acceptanceCriteria`, `archDecisions`, `parent`, `localId` ← parse
     the body's `## Summary` / `## Acceptance criteria` / `## Architecture decisions touched`
     / `## Meta` sections (the schema's rendered template).
   - `number`, `nodeId`, `url`, `githubUpdatedAt` ← from the issue.
   - **Normalize text** (title as plain text; summary / criteria / decisions as Markdown)
     per the schema's *Text encoding* section, so no HTML entities enter the mirror.
3. **Merge into `github-issues.json`:** update items matched by `number`, append new ones,
   and leave local-only items (`number: null`) untouched. Set each synced item's
   `baseSnapshot` to its current content hash (the 3-way-merge base) and the top-level
   `syncedAt`.
4. **Final pass:** `python3 .claude/skills/_shared/wi_text.py mirror` (idempotent).
5. **Never commit the mirror** (it's git-ignored).

## Notes
- The authoritative status is the `status:*` label; open/closed state and board field
  values may also be captured for reference.
- This is the read primitive that `wi-sync` builds on.
