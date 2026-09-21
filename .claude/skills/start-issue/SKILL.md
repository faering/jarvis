---
name: start-issue
description: Begin work on a GitHub issue — create the branch (always-PR convention), move its Project board card to In Progress, and self-assign. Use when starting to implement a tracked work item (issue number).
---

# start-issue

Standardized entry point for working an issue. **All GitHub reads/writes go through the
GitHub MCP** (`mcp__github__*`), not `gh` (see [[reference-github-token-split]] and
`_shared/issue-schema.md`).

## Inputs
- An **issue number** (e.g. `#24`). If given a work item's local id, resolve its number
  from `github-issues.json` first.

## Steps
1. **Read the issue** — `issue_read` (or the local mirror) for its title and `type:*` label.
2. **Derive the branch name** — `<type>/<issue>-<slug>`:
   - type from the issue's `type:*` label → `feature`→`feat`, `bug`→`fix`, `task`→`chore`,
     `story`/`epic`→`feat`; a docs-only item → `docs`; CI/infra → `ci`/`chore`.
   - `slug` = the title, lowercased, non-alphanumerics → `-`, trimmed, ≤ 6 words.
   - e.g. issue #24 "Agent service skeleton …" → `feat/24-agent-service-skeleton`.
3. **Cut the branch off fresh `main`** (never work on `main` — see [[feedback-always-pr]]):
   ```bash
   git checkout main && git pull --ff-only origin main
   git checkout -b <branch>
   ```
   (Push auth uses the local credential helper: `git config --local
   credential.https://github.com.helper '!gh auth git-credential'`.)
4. **Move the board card to In Progress** — `projects_write update_project_item`
   (owner `faering`, project 3), resolving the item by `item_owner/item_repo/issue_number`:
   `updated_field {"name":"Status","value":"In Progress"}`. Also flip the issue's
   `status:*` label to `status:in-progress` via `issue_write update`.
5. **Self-assign** — `issue_write update` with `assignees: ["faering"]` (confirm the login
   with `get_me` if unsure).

## Then
Implement, committing per the Conventional-Commits + commit↔issue rules in AGENTS.md, and
finish with the `open-pr` skill (PR body carries `Closes #<n>`; **rebase-only** merge; no
attribution lines).

## Notes
- Don't set the card to **Done** by hand — the PR closing the issue drives that (a board
  workflow moves closed issues to Done).
