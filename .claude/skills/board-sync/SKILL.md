---
name: board-sync
description: Sync GitHub issues onto the Jarvis Project (v2) board — add items and set Status / Item Type / Priority / Sprint fields, creating any missing single-select fields. Use after creating/updating issues or to reconcile the board with github-issues.json.
---

# board-sync

Keeps the **Jarvis Project #3** board (`PVT_kwHOAewEFs4BkOgt`,
https://github.com/users/faering/projects/3) in step with the repo's issues and the local
mirror. Field value mapping and the work-item shape live in `_shared/issue-schema.md`.

## Token model (important — see [[reference-github-token-split]])
- **Item add + field updates → GitHub MCP** (`projects_write`). It uses `GITHUB_PAT`
  (project-capable). Prefer it.
- **Creating single-select fields or changing project visibility → GraphQL with
  `GITHUB_PAT`** (`gh api graphql`), because the MCP has no method for it and the `gh`
  classic token lacks `project` scope (`gh project …` → "unknown owner type").

## Board fields
| Field | Kind | Values | Source |
|-------|------|--------|--------|
| Status | built-in single-select | Todo / In Progress / Done | issue `status:*` (see mapping) |
| Item Type | single-select | Epic / Feature / Story / Task / Bug | issue `type:*` |
| Priority | single-select | P0 / P1 / P2 / P3 | issue `prio:*` |
| Sprint | iteration (14d) | — | assigned during planning |

Status label→field: `backlog`/`ready`→**Todo**, `in-progress`/`review`→**In Progress**,
`done`→**Done** (the board keeps a coarse 3-state column; the 5-state truth is the label).

## Steps
1. **Ensure fields exist.** List fields (`gh api graphql` `node(...).fields`). Create any
   missing single-select via `createProjectV2Field` (dataType `SINGLE_SELECT`,
   `singleSelectOptions`), `GH_TOKEN=$GITHUB_PAT`. NB: **"Type" is reserved** — the field is
   named **"Item Type"**.
2. **Add items.** For each issue not on the board, `projects_write add_project_item`
   (`item_owner`/`item_repo`/`issue_number`). Idempotent — returns the existing item; the
   repo's auto-add workflow also adds new issues, so this mostly backfills.
3. **Set fields in bulk.** Group issues by value and call `projects_write
   update_project_items` once per (field, value) — up to 50 items, referencing each by
   `{item_owner,item_repo,issue_number}`, `updated_field {"name": <field>, "value": <option>}`.
   Example: all `type:epic` issues → `{"name":"Item Type","value":"Epic"}`.
4. **Reconcile the mirror.** Write project number/url/field state into `github-issues.json`
   (`project` block). The mirror is git-ignored — never commit it.

## Notes
- Setting **Status = Done** closes the issue (board workflow). Don't do it manually to
  "mark done" — let the closing PR drive it.
