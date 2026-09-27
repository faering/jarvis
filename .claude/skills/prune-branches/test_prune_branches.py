"""Tests for prune_branches.plan (pure; no git or gh needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from prune_branches import PullRequest, plan  # noqa: E402

A, B = "a" * 40, "b" * 40


def decide(prs, remote=None, local=None, **kw):
    return {
        (d.where, d.branch): (d.delete, d.reason)
        for d in plan(prs, remote or {}, local or {}, **kw)
    }


class PlanTest(unittest.TestCase):
    def test_merged_branch_at_pr_head_is_deleted_remote_and_local(self):
        prs = [PullRequest(1, "MERGED", "feat/x", A)]
        got = decide(prs, remote={"feat/x": A}, local={"feat/x": A})
        self.assertEqual(got[("remote", "feat/x")], (True, "PR #1 merged"))
        self.assertEqual(got[("local", "feat/x")], (True, "PR #1 merged"))

    def test_commits_after_merge_are_kept(self):
        prs = [PullRequest(1, "MERGED", "feat/x", A)]
        got = decide(prs, local={"feat/x": B})
        self.assertEqual(got[("local", "feat/x")], (False, "commits after PR #1"))

    def test_open_pr_wins_over_an_older_merged_one(self):
        prs = [PullRequest(1, "MERGED", "feat/x", A), PullRequest(2, "OPEN", "feat/x", B)]
        self.assertEqual(
            decide(prs, remote={"feat/x": B})[("remote", "feat/x")], (False, "PR open")
        )

    def test_newest_pr_decides(self):
        prs = [PullRequest(1, "MERGED", "feat/x", A), PullRequest(2, "CLOSED", "feat/x", A)]
        got = decide(prs, remote={"feat/x": A})
        self.assertEqual(got[("remote", "feat/x")], (False, "PR #2 closed, not merged"))

    def test_closed_unmerged_only_with_flag(self):
        prs = [PullRequest(3, "CLOSED", "feat/y", A)]
        self.assertFalse(decide(prs, remote={"feat/y": A})[("remote", "feat/y")][0])
        got = decide(prs, remote={"feat/y": A}, include_closed=True)
        self.assertEqual(got[("remote", "feat/y")], (True, "PR #3 closed"))

    def test_protected_current_and_worktree_branches_are_kept(self):
        prs = [PullRequest(1, "MERGED", n, A) for n in ("main", "feat/cur", "feat/wt")]
        got = decide(
            prs,
            remote={"main": A},
            local={"main": A, "feat/cur": A, "feat/wt": A},
            current="feat/cur",
            worktrees=["feat/wt"],
        )
        self.assertEqual(got[("remote", "main")], (False, "protected"))
        self.assertEqual(got[("local", "feat/cur")], (False, "checked out"))
        self.assertEqual(got[("local", "feat/wt")], (False, "checked out"))

    def test_checked_out_only_protects_the_local_branch(self):
        prs = [PullRequest(1, "MERGED", "feat/cur", A)]
        got = decide(prs, remote={"feat/cur": A}, local={"feat/cur": A}, current="feat/cur")
        self.assertTrue(got[("remote", "feat/cur")][0])
        self.assertFalse(got[("local", "feat/cur")][0])

    def test_branch_without_pr_and_fork_prs_are_ignored(self):
        prs = [PullRequest(1, "MERGED", "feat/z", A, fork=True)]
        got = decide(prs, remote={"feat/z": A, "scratch": B})
        self.assertEqual(got[("remote", "feat/z")], (False, "no PR"))
        self.assertEqual(got[("remote", "scratch")], (False, "no PR"))


if __name__ == "__main__":
    unittest.main()
