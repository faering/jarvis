---
name: wi-push
description: Create or update GitHub issues from local edits in github-issues.json, ensure the labels exist, and add items to the Project board. Use after editing the local mirror to push changes up, or as the write half of wi-sync.
---

# wi-push

Pushes local mirror edits up to GitHub. MCP-first; see `_shared/issue-schema.md` and
[[reference-github-token-split]].

## Steps
1. **Ensure labels** for the taxonomy (`type:*`, `prio:*`, `status:*`) exist. Missing ones
   are created with `gh label create` (the `gh` classic token has `repo`). Label creation is
   the one routine op still on `gh`; everything else here is MCP.
2. **Normalize before sending** — run `python3 .claude/skills/_shared/wi_text.py mirror`,
   and pass titles/bodies to MCP as **raw text** (`&`, `->`), never HTML-escaped. See the
   schema's *Text encoding* section.
3. **New items** (`number: null`): `issue_write create` with `title`, the schema-rendered
   `body`, `labels`, and `parent_issue_number` (creates the sub-issue link in the same call).
   Write the returned `number`/`url`/`nodeId` back into the mirror.
4. **Changed items** (have `number`, content differs from `baseSnapshot`): `issue_write
   update` — title / body / labels / state.
5. **Verify** — for each written issue, re-read the stored title and body and pipe them
   through `wi_text.py check`. If entities show up, fix them with an update before moving
   on.
6. **Board** — hand new and changed items to `board-sync` (add to Project #3 + set
   Status / Item Type / Priority).
7. **Bookkeeping** — update each pushed item's `baseSnapshot` and the top-level `syncedAt`.
   Never commit the mirror.

## Notes
- To *close* a work item, prefer letting its PR close the issue (`Closes #n`); only set
  `state: closed` here for items with no code of their own (e.g. a decision record).
- Idempotent: re-running skips items whose content already matches `baseSnapshot`.
