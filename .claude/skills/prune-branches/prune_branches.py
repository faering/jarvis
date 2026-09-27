#!/usr/bin/env python3
"""Delete branches whose pull request was merged into main (remote and local).

A branch is deleted only when all of these hold:
- its newest PR is MERGED (or CLOSED, with --include-closed) and none is still OPEN,
- the branch still points at that PR's head commit (so nothing was added after merging),
- it is not the default branch, not checked out here, and not in another worktree.

Rebase merges rewrite commits, so "merged" comes from the PR state, never from
`git branch --merged`. Dry run by default; --apply deletes. Stdlib only; uses `gh` and `git`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass

PROTECTED = {"main", "master", "HEAD"}


@dataclass(frozen=True)
class PullRequest:
    number: int
    state: str  # OPEN | MERGED | CLOSED
    head: str
    sha: str
    fork: bool = False


@dataclass(frozen=True)
class Decision:
    branch: str
    where: str  # remote | local
    delete: bool
    reason: str


def plan(
    prs: Iterable[PullRequest],
    remote: dict[str, str],
    local: dict[str, str],
    *,
    current: str | None = None,
    worktrees: Iterable[str] = (),
    include_closed: bool = False,
) -> list[Decision]:
    """Decide, per remote and local branch, whether to delete it and why."""
    by_head: dict[str, list[PullRequest]] = {}
    for pr in prs:
        if not pr.fork:
            by_head.setdefault(pr.head, []).append(pr)
    busy = set(worktrees) | ({current} if current else set())
    deletable = {"MERGED", "CLOSED"} if include_closed else {"MERGED"}

    decisions = []
    for where, refs in (("remote", remote), ("local", local)):
        for branch, sha in sorted(refs.items()):
            decisions.append(_decide(branch, where, sha, by_head.get(branch, []), busy, deletable))
    return decisions


def _decide(
    branch: str,
    where: str,
    sha: str,
    prs: list[PullRequest],
    busy: set[str],
    deletable: set[str],
) -> Decision:
    def keep(reason: str) -> Decision:
        return Decision(branch, where, False, reason)

    if branch in PROTECTED:
        return keep("protected")
    if where == "local" and branch in busy:
        return keep("checked out")
    if not prs:
        return keep("no PR")
    if any(pr.state == "OPEN" for pr in prs):
        return keep("PR open")
    newest = max(prs, key=lambda pr: pr.number)
    if newest.state not in deletable:
        return keep(f"PR #{newest.number} {newest.state.lower()}, not merged")
    if sha != newest.sha:
        return keep(f"commits after PR #{newest.number}")
    return Decision(branch, where, True, f"PR #{newest.number} {newest.state.lower()}")


def _run(*cmd: str) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def _refs(pattern: str, strip: str) -> dict[str, str]:
    out = _run("git", "for-each-ref", "--format=%(refname) %(objectname)", pattern)
    refs = {}
    for line in out.splitlines():
        name, sha = line.split()
        refs[name.removeprefix(strip)] = sha
    return refs


def _worktree_branches() -> list[str]:
    out = _run("git", "worktree", "list", "--porcelain")
    return [
        line.removeprefix("branch refs/heads/")
        for line in out.splitlines()
        if line.startswith("branch refs/heads/")
    ]


def _pull_requests() -> list[PullRequest]:
    out = _run(
        "gh", "pr", "list", "--state", "all", "--limit", "1000",
        "--json", "number,state,headRefName,headRefOid,isCrossRepository",
    )  # fmt: skip
    return [
        PullRequest(
            p["number"], p["state"], p["headRefName"], p["headRefOid"], p["isCrossRepository"]
        )
        for p in json.loads(out)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    parser.add_argument(
        "--include-closed", action="store_true", help="also delete branches of closed, unmerged PRs"
    )
    parser.add_argument("--remote", default="origin")
    args = parser.parse_args(argv)

    _run("git", "fetch", "--prune", "--quiet", args.remote)
    prefix = f"refs/remotes/{args.remote}/"
    remote = _refs(prefix, prefix)
    local = _refs("refs/heads/", "refs/heads/")
    current = _run("git", "branch", "--show-current").strip() or None
    decisions = plan(
        _pull_requests(),
        remote,
        local,
        current=current,
        worktrees=_worktree_branches(),
        include_closed=args.include_closed,
    )

    doomed = [d for d in decisions if d.delete]
    for d in decisions:
        mark = "delete" if d.delete else "keep  "
        print(f"{mark} {d.where:6} {d.branch}  ({d.reason})")
    if not doomed:
        print("Nothing to delete.")
        return 0
    if not args.apply:
        print(f"\nDry run: {len(doomed)} to delete. Re-run with --apply.")
        return 0

    remote_names = [d.branch for d in doomed if d.where == "remote"]
    local_names = [d.branch for d in doomed if d.where == "local"]
    status = 0
    if remote_names:
        try:
            _run("git", "push", args.remote, "--delete", *remote_names)
        except subprocess.CalledProcessError as err:
            # e.g. a ruleset restricting deletions; the local cleanup still runs.
            print(f"\nRemote deletion rejected:\n{err.stderr.strip()}", file=sys.stderr)
            remote_names, status = [], 1
    if local_names:
        _run("git", "branch", "-D", *local_names)
    print(f"\nDeleted {len(remote_names)} remote and {len(local_names)} local branches.")
    return status


if __name__ == "__main__":
    sys.exit(main())
