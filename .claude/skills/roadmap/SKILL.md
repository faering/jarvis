---
name: roadmap
description: Plan and keep the Jarvis Project roadmap current — set/shift Start date, Target date, Sprint and Milestone on issues and epics, check items against milestone due dates, keep epics spanning their children, record actual dates on close, and show the timeline as text. Use when planning work, when asked "what's planned when", after closing or starting issues, or to reconcile the Roadmap view.
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
| Milestone | repo milestone (one per issue), with a due date | the **Jarvis release** the item ships in |

The Roadmap view must use Start/Target date for its bars and show milestones as markers:
one-time UI settings (view menu → Date fields, and → Markers → Milestones); the API can't
set them.

**One milestone = one Jarvis release** (#162): `Jarvis N: <outcome>` ("Jarvis 1: Lives on
the Pi"), an outcome you could demo. The description holds the outcome and, once the user
names it, `Codename: <Marvel/DC superhero>.` (read by `jarvis-release`). Jarvis releases
(tag `jarvis-vN.M`) pin a tested set of independently released components (ADR 0004) in
`releases/jarvis-N.toml`.
The plan is **derived from the issues**, never hand-written: features/stories → Added,
bugs → Fixed, `change:changed` / `change:deprecated` labels → Changed / Deprecated.

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
7. **Every open feature, story, task and bug has a milestone;** an epic gets one only when
   all its open children share it (an issue holds one milestone). `new-issue` proposes one;
   `start-issue` sets one if missing and says which.
8. **Items fit their milestone:** a target date after the milestone's due date is an
   **overrun**. Report it with two options (move the item to the next milestone, or move the
   due date) and apply on OK. Never move a due date silently.

## Commands
- **`sync`** — apply rules 1, 3 and report 6, 7 (items without a milestone) and 8.
  Safe to run anytime; `board-sync` calls it.
- **`plan <issues|epic>`** — rule 5.
- **`shift <issue> <days|date>`** — move start/target, then re-run rule 1 for its epic.
- **`show [epic|sprint|milestone]`** — text timeline: per milestone (due date, closed/total),
  then per epic, children with start → target, status, overdue/overrun flag.
- **`milestones`** — list open milestones: due date, progress, overruns, items missing one.
- **`milestone add <title> <due> <outcome>`** — propose, then create on OK.
- **`plan-release <milestone>`** — the derived Added/Changed/Deprecated/Fixed list for a
  milestone, for review or to cut the release. Before the milestone is done, list its open
  and closed issues by those rules (open ones marked). To cut it, follow
  [docs/deploy.md "Cut a Jarvis release"](../../../docs/deploy.md#cut-a-jarvis-release):
  `scripts/release/jarvis-release draft --milestone "<title>" --codename "<name>"` writes
  `releases/jarvis-N.toml` + `.md` (closed issues only) and the README roadmap block; ask the
  user for the codename if the milestone has none, and never merge the release PR.
- **README roadmap** — `sync` also runs `scripts/release/jarvis-release readme --check`; if
  the milestones changed (title, due date, codename, closed), regenerate the block with
  `scripts/release/jarvis-release readme` in a PR.

## How
Read items with dates (GraphQL, `GITHUB_PAT`):
```bash
GH_TOKEN=$GITHUB_PAT gh api graphql -f query='{user(login:"faering"){projectV2(number:3){
  items(first:100){nodes{content{... on Issue{number title state closedAt}}
  fieldValues(first:20){nodes{... on ProjectV2ItemFieldDateValue{date field{... on ProjectV2FieldCommon{name}}}
  ... on ProjectV2ItemFieldIterationValue{title field{... on ProjectV2FieldCommon{name}}}}}}}}}}'
```
(paginate with `after:` beyond 100 items). Add `milestone{number title dueOn}` to the
`... on Issue` fragment to read milestones. Parents come from the issue's sub-issue parent
(`issue_read`) or the `Parent:` line in its body.

Write dates in bulk with `projects_write update_project_items`
(`updated_field {"name":"Start date","value":"YYYY-MM-DD"}`), grouping items per value
(≤ 50 per call). Sprint: `{"name":"Sprint","value":"<iteration title>"}`.

Milestones (repo REST, the `gh` token is enough):
```bash
gh api repos/faering/jarvis/milestones -q '.[]|{number,title,due_on,open_issues,closed_issues}'
gh api repos/faering/jarvis/milestones -f title='Jarvis lives on the Pi' \
  -f due_on=2026-10-11T23:59:59Z -f description='<outcome, one line>'
```
Assign with MCP `issue_write update` (`milestone: <number>`).

Mirror `startDate`/`targetDate`/`milestone` into `github-issues.json` (schema: `_shared/issue-schema.md`).

## Notes
- Sparring applies here too: if a plan looks unrealistic (too much in one sprint, a P1
  behind a P3), say so and propose an alternative instead of just applying it.
