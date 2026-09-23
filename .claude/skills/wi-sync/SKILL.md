---
name: wi-sync
description: Reconcile github-issues.json with GitHub in both directions using a 3-way merge (baseSnapshot as the base), resolving per-item conflicts. Use to bring the local mirror and GitHub back in step when both may have changed.
---

# wi-sync

Two-way reconcile. GitHub is source of truth, but local edits can be pushed; genuine
conflicts are resolved per item against each item's `baseSnapshot` (its last-synced
content). Shape + fields: `_shared/issue-schema.md`.

## Per-item decision (base = `baseSnapshot`)
| local vs base | remote vs base | action |
|---------------|----------------|--------|
| changed       | unchanged      | **push** local (`wi-push`) |
| unchanged     | changed        | **pull** remote (`wi-fetch`) |
| unchanged     | unchanged      | no-op |
| changed       | changed        | **CONFLICT** |

## Steps
1. `wi-fetch` remote state into memory (don't overwrite local yet); compute remote-vs-base
   and local-vs-base for each item. Compare **normalized** text on both sides (schema
   *Text encoding* section) so entity/CRLF noise never counts as a change.
2. Apply the table. For **conflicts**, show a field-level diff and resolve by
   `--prefer github|json` (bulk) or interactively per field.
3. After each push / pull / resolve, rewrite the item's `baseSnapshot`, `githubUpdatedAt`,
   and the top-level `syncedAt`.
4. Never commit the mirror.

## Notes
- New local items (`number: null`) are always pushes; new remote items are always pulls.
- Orchestrates the `wi-fetch` + `wi-push` primitives — keep the merge logic here and the
  I/O in those.
