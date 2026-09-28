---
name: jarvis-release
description: Cut a named Jarvis release ("Jarvis N — <Codename>") for a milestone - check it's ready, draft the manifest and notes, open the release PR for the user to merge, then verify what got published. Use when the user asks to release Jarvis N or cut a Jarvis release.
---

# jarvis-release

A Jarvis release names a tested agent+app pair for a milestone (#162). It builds and
deploys nothing. Only the user's merge of the release PR publishes it. How it works:
[docs/deploy.md "Cut a Jarvis release"](../../../docs/deploy.md#cut-a-jarvis-release).

## Steps
1. **Readiness** (report; ask before changing anything):
   - the milestone's open issues: each must be closed or moved to the next milestone, which is the user's call
   - the codename: in the milestone description, otherwise ask; one per major number
   - the component releases to pin: default the newest with `manifest.json`; say which, and
     whether they're what's deployed on the Pi
2. **Draft in a temporary worktree**, never the user's checkout:
   ```bash
   git worktree add -b release/jarvis-<N> <tmp> origin/main && cd <tmp>
   scripts/release/jarvis-release draft --milestone "<title>" --codename "<name>"
   scripts/release/jarvis-release check
   ```
   Show the user the notes (`releases/jarvis-<N>.md`) and the pinned versions.
3. **Open the PR** (`chore(repo): release Jarvis <N> — <Codename>`). The body gives the
   pinned versions, a link to the notes, and `Refs` for the milestone's issues. **No
   closing keywords anywhere**: CI refuses them in the notes. Remove the worktree.
4. **Hand over.** The user merges; never merge, and don't wait on CI
   ([[feedback-never-merge-prs]], [[feedback-dont-wait-for-ci]]).
5. **After the merge, when asked:** verify that
   - tag `jarvis-vN.M` exists
   - the GitHub release is titled "Jarvis N — <Codename>" with its notes and manifest, and is Latest
   - the milestone is closed
   - the README roadmap is current (`scripts/release/jarvis-release readme --check`)

## Notes
- `N.1`, `N.2`: a later tested pair for the same milestone keeps the codename. `draft`
  picks the next free minor.
- Deploying a Jarvis release as one set is #163. Until then, each component deploys on its own.
