---
paths:
  - "scripts/**"
  - ".claude/skills/**"
  - ".github/workflows/**"
  - "**/test_*.py"
  - "**/test_*.sh"
---

# Git in tests and scripts

Git hooks (pre-commit, pre-push) run with `GIT_DIR` / `GIT_WORK_TREE` set for the real
repo. Any git command a test or script runs inherits them and acts on the real repo, even
with `git -C <tmp>`. On 2026-09-28 a test's `git init` / `git config` rewrote the real
`.git/config` (worktree, identity, signing).

- **Clear every `GIT_*` variable** before a test or script runs git in a scratch repo
  (e.g. drop them from `os.environ` at the top of a Python test module).
- **Scratch repos only:** `tempfile` directories, with their own `user.*` and
  `commit.gpgsign` / `tag.gpgsign` (`false`) set **inside** them. Never `git config
  --global`, never the real repo.
- **Run it like the hook does** before pushing:
  `GIT_DIR=$(git rev-parse --git-dir) GIT_WORK_TREE=$PWD <test command>`.
- **Agents never change the user's git config.** If it's wrong, show the commands.
