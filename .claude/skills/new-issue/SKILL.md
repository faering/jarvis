---
name: new-issue
description: File a new GitHub issue that matches the Jarvis work-item schema — labels, parent (sub-issue), board fields, and the local mirror. Use to create a tracked work item (epic/feature/story/task/bug).
---

# new-issue

Creates a schema-compliant work item. MCP-first. Shape: `_shared/issue-schema.md`.

## Gather (ask if any are missing or ambiguous)
- `title`, `type` (epic/feature/story/task/bug), `summary`, acceptance criteria,
  `priority` (P0–P3), `parent` (issue #), architecture decisions touched.

## Steps
1. **De-dupe** — `search_issues` for an existing match first.
2. Ensure the `type:*` / `prio:*` / `status:*` labels exist (`gh label create` if missing).
3. `issue_write create` with `title`, the schema-rendered `body` (Summary / Acceptance
   criteria / Architecture decisions touched / Meta), `labels`, and `parent_issue_number`
   for the sub-issue link. Pass title and body as **raw text** (`&`, `->`), never
   HTML-escaped; then re-read the stored title and run it through
   `python3 .claude/skills/_shared/wi_text.py check` (schema *Text encoding* section).
4. `board-sync` the new issue (add to Project #3 + set Status / Item Type / Priority).
5. Append it to `github-issues.json` with the returned `number`/`url`/`nodeId` (the mirror
   is git-ignored — don't commit it).

## Notes
- Default `status: backlog`; if you're starting the work now, use `start-issue` instead of
  (or right after) filing.
