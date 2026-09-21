# Jarvis Work-Item Schema

Canonical shape for every Jarvis work item. All issue-related skills (`new-issue`,
`plan-issue`, `open-pr`, `wi-fetch`, `wi-push`, `wi-sync`) reference this file so the
shape is defined once. **GitHub is the source of truth; `github-issues.json` is a local
mirror.**

## Why labels + a Project (not native Issue Types)

Native GitHub *Issue Types* are organization-only and unavailable on personal repos.
Reliable *sub-issues* are similarly gated. So on this repo we model:

- **Item type** via a `type:*` label.
- **Hierarchy** via a `parent` field (the parent issue number) plus a task-list in the
  parent's body (`- [ ] #NN`), which GitHub renders as tracked progress. Native
  sub-issues are used opportunistically only if the account exposes the API.
- **Board / roadmap** via a user-level **GitHub Project (v2)** whose custom fields mirror
  the labels (Type, Priority, Status, Iteration).

**Issues are the target; the Project is a view added on top.** `wi-push` creates/updates
**repo issues** (the primitive that carries body, labels, comments, sub-issues, and
commit/PR closing-links), and `github-issues.json` mirrors those issues. A Project item is
only a *reference* to an issue (or a lightweight draft) with no commit-linking, so we never
push work items straight into a Project. Adding issues to the Project happens separately and
at any time — manually, via the Project's built-in auto-add workflow, or via the API/MCP
(`projects_write`) — and is what the **Project bootstrap** work item (f2.3) does: create the
Project + fields, add the issues, and set their field values. The `project` block below
caches the Project number + field IDs so `wi-push`/`wi-sync` can set those fields.

## Item types & hierarchy

```
Epic ─▶ Feature ─▶ Story ─▶ Task
Bug (attaches under any of the above via `parent`, or stands alone)
```

## Label taxonomy

| Dimension | Labels |
|-----------|--------|
| Type      | `type:epic` `type:feature` `type:story` `type:task` `type:bug` |
| Priority  | `prio:P0` `prio:P1` `prio:P2` `prio:P3` |
| Status    | `status:backlog` `status:ready` `status:in-progress` `status:review` `status:done` |

`status:*` labels mirror the Project's **Status** field; keep them in sync.

## Issue fields

Every work item has:

- **title** — imperative, concise (e.g. "Add WebSocket API to agent service").
- **type** — one of the types above.
- **summary** — 1–3 sentences: what and why.
- **acceptance criteria** — checklist of verifiable outcomes (`- [ ]`).
- **priority** — `P0`–`P3`.
- **status** — one of the statuses above.
- **parent** — parent issue number, or `null` for a top-level Epic.
- **iteration** — sprint/iteration name, or `null`.
- **labels** — the resolved `type:*`/`prio:*`/`status:*` set plus any extras.
- **architecture decisions touched** — which CLAUDE.md decisions this item affects
  (language boundaries, compute-layer routing, Docker/Tauri split, CI/CD). Required so
  `plan-issue` can check work against the project brief.

### Rendered issue body template

```markdown
## Summary
<what & why>

## Acceptance criteria
- [ ] ...
- [ ] ...

## Architecture decisions touched
- <decision + how>

## Meta
- Parent: #<n | none>
- Iteration: <name | none>
```

## Local mirror: `github-issues.json`

Envelope:

```jsonc
{
  "schemaVersion": 1,
  "syncedAt": "<ISO-8601 | null>",     // last successful sync with GitHub
  "project": {
    "number": null,                     // GitHub Project (v2) number, once bootstrapped
    "url": null,
    "fields": {}                        // field-id map cached for pushes
  },
  "items": [ /* WorkItem[] */ ]
}
```

`WorkItem`:

```jsonc
{
  "localId": "e1",                      // stable local id; survives before a GitHub number exists
  "number": null,                       // GitHub issue number (null until pushed)
  "nodeId": null,                       // GraphQL node id (for Project ops)
  "url": null,

  "type": "epic",                       // epic|feature|story|task|bug
  "title": "Dev Environment & Standards",
  "summary": "…",
  "acceptanceCriteria": ["…"],
  "priority": "P1",                     // P0..P3
  "status": "backlog",                  // backlog|ready|in-progress|review|done
  "parent": null,                       // parent's localId or GitHub number
  "iteration": null,
  "labels": ["type:epic", "prio:P1", "status:backlog"],
  "archDecisions": ["…"],

  // Sync bookkeeping (see below)
  "githubUpdatedAt": null,              // remote updatedAt at last sync
  "localUpdatedAt": "<ISO-8601>",       // bumped on any local edit
  "baseSnapshot": null                  // content hash/snapshot at last sync = merge base
}
```

## Sync: 3-way merge with per-item conflict resolution

`baseSnapshot` records each item's content at the moment it was last in sync. On sync,
compare current **local** and **remote** against that base:

| local vs base | remote vs base | action |
|---------------|----------------|--------|
| changed       | unchanged      | **push** local → GitHub |
| unchanged     | changed        | **pull** remote → JSON |
| unchanged     | unchanged      | no-op |
| changed       | changed        | **CONFLICT** |

On conflict, show a field-level diff and resolve by:
- `--prefer github` or `--prefer json` (bulk), or
- interactive per-field choice.

After any push/pull/resolve, rewrite `baseSnapshot`, `githubUpdatedAt`, and `syncedAt`.
The base snapshot is what makes reliable "pick the correct side" possible instead of
last-writer-wins.

Skills:
- **`wi-fetch`** — pull all issues from GitHub into the mirror.
- **`wi-push`** — create/update GitHub issues (and Project items) from local edits.
- **`wi-sync`** — reconcile both directions using the table above.
