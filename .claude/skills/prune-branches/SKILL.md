---
name: prune-branches
description: Delete remote and local branches whose PRs were merged into main (never branches with open PRs, new commits, or a worktree). Use after the user merges PRs, at the start of start-issue, or when asked to clean up branches.
---

# prune-branches

Deletes the head branches of merged PRs, on `origin` and locally. Rebase merges rewrite
commits, so "merged" comes from the **PR state**, never from `git branch --merged`.

## Safety rules (enforced by the script)
- Delete only if the newest PR for the branch is **MERGED**, no PR for it is **OPEN**, and the
  branch still points at that PR's **head commit** (nothing added after merging).
- Never `main`, the current branch, or a branch checked out in a worktree.
- Branches of **closed, unmerged** PRs are kept unless `--include-closed`, which needs the
  user's OK first (they may hold work worth keeping).
- Branches without any PR (scratch work, release-please before its PR) are kept.

## Steps
1. Dry run and show the user the `delete` lines:
   ```bash
   python3 .claude/skills/prune-branches/prune_branches.py
   ```
2. Apply (no need to ask for merged-PR branches; that's the standing instruction):
   ```bash
   python3 .claude/skills/prune-branches/prune_branches.py --apply
   ```
3. Remove leftover worktrees whose branch is gone: `git worktree prune`.

## Notes
- Remote deletion needs the `pr-branches-linear-history` ruleset **not** to restrict
  deletions; if `git push --delete` is rejected by a rule, report it instead of retrying.
- GitHub's "Automatically delete head branches" setting covers new merges once that rule is
  off; this skill covers the backlog and local branches.
- Tests: `python3 .claude/skills/prune-branches/test_prune_branches.py`.
