---
name: roadmap
description: Plan and keep the Jarvis Project roadmap current — set/shift Start date, Target date and Sprint on issues and epics, keep epics spanning their children, record actual dates on close, and show the timeline as text. Use when planning work, when asked "what's planned when", after closing or starting issues, or to reconcile the Roadmap view.
---

# roadmap

Keeps the **Roadmap** view of Project #3 (https://github.com/users/faering/projects/3) true.
It is also driven automatically: `start-issue` sets the start, `open-pr` and `board-sync`
reconcile. Token model: [[reference-github-token-split]] (writes via MCP `projects_write`,
reads via GraphQL with `GITHUB_PAT`).

## Fields
| Field | Kind | Meaning |
|-------|------|---------|
| `Start date` | DATE | work actually started (set by `start-issue`) or planned start |
| `Target date` | DATE | planned finish; on close, the **actual** close date |
| `Sprint` | iteration (14d) | the sprint the item lands in |

The Roadmap view must use Start/Target date for its bars: a one-time UI setting (view menu →
Date fields); the API can't set it.

## Rules
1. **Epics span their children:** start = earliest child start, target = latest child
   target (ignore children without dates).
2. **Children fit their epic;** a child scheduled past its epic extends the epic, and you say so.
3. **Closed items** get `Target date` = actual close date (and a start, if missing, from
   their first linked PR's creation date). Never move a closed item otherwise.
4. **Starting an issue** (`start-issue`): `Start date` = today, `Sprint` = current sprint. If
   `Target date` is empty, set a provisional one by size (task +2d, feature +7d, spike +3d;
   P1 items no later than the sprint end) and **say so** in chat, so it can be challenged.
5. **Planning new/unstarted work** (`plan`): propose dates in chat first (a short table:
   item, start, target, sprint, why); apply only after the user's OK. Respect priority
   (P0/P1 first), dependencies ("Blocked by" in the issue body) and the user's capacity
   (subagent batches ≈ one day of work each).
6. **Overdue** open items (target < today): don't silently shift. Report them with a
   suggested new date and apply on OK — the slip itself is useful information.

## Commands
- **`sync`** — apply rules 1, 3 and report 6. Safe to run anytime; `board-sync` calls it.
- **`plan <issues|epic>`** — rule 5.
- **`shift <issue> <days|date>`** — move start/target, then re-run rule 1 for its epic.
- **`show [epic|sprint]`** — text timeline: per epic, children with start → target, status,
  overdue flag.

## How
Read items with dates (GraphQL, `GITHUB_PAT`):
```bash
GH_TOKEN=$GITHUB_PAT gh api graphql -f query='{user(login:"faering"){projectV2(number:3){
  items(first:100){nodes{content{... on Issue{number title state closedAt}}
  fieldValues(first:20){nodes{... on ProjectV2ItemFieldDateValue{date field{... on ProjectV2FieldCommon{name}}}
  ... on ProjectV2ItemFieldIterationValue{title field{... on ProjectV2FieldCommon{name}}}}}}}}}}'
```
(paginate with `after:` beyond 100 items). Parents come from the issue's sub-issue parent
(`issue_read`) or the `Parent:` line in its body.

Write dates in bulk with `projects_write update_project_items`
(`updated_field {"name":"Start date","value":"YYYY-MM-DD"}`), grouping items per value
(≤ 50 per call). Sprint: `{"name":"Sprint","value":"<iteration title>"}`.

Mirror `startDate`/`targetDate` into `github-issues.json` (schema: `_shared/issue-schema.md`).

## Notes
- Sparring applies here too: if a plan looks unrealistic (too much in one sprint, a P1
  behind a P3), say so and propose an alternative instead of just applying it.
