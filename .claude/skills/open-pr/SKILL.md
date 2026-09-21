---
name: open-pr
description: Open a pull request for the current branch — draft the description from the diff and link the issue it closes. MCP-first. Use when a work item's branch is ready for review.
---

# open-pr

Opens the PR that finishes a work item. Always-PR, rebase-only, and **no attribution
lines** (see [[feedback-no-attribution]] and [[feedback-always-pr]]).

## Preconditions
- On a feature branch (never `main`), commits present and pushed, working tree clean.

## Steps
1. Review `git diff main..HEAD` and the commit log; summarize what changed and why.
2. Draft the PR body: a short "What's in it" summary + **`Closes #<n>`** for the work item.
   Put the closing keyword in the **PR body** (survives squash) and **repeat the keyword per
   issue** — `Closes #1, closes #2` (see the linking rules in AGENTS.md). Use `Refs #<n>` for
   related-but-not-closed.
3. `create_pull_request` (base `main`, head = current branch). **No `Co-Authored-By` or
   Claude attribution anywhere.**
4. Leave the board card In Progress; the closing PR + board workflow move it to Done on
   merge.

## Notes
- Merges are **rebase-only**; `main` requires a PR (the "main protection" ruleset). Never
  merge a PR unless asked.
- If several unrelated concerns are staged, split them into separate PRs.
