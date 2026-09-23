# 0004. Independent per-component releases
Status: Accepted · Date: 2026-09-23

## Context
The agent (Docker image) and the app (Tauri binary) change at different speeds. We want to
ship a stable app while the agent keeps iterating, and every build should say exactly what
it is.

## Decision
- **release-please** versions each component separately: `agent-vX.Y.Z` and `app-vX.Y.Z`.
- **Routing:** it assigns each commit to a component by the files it touches. The commit
  type sets the version bump.
- **Release PRs are the human gate.** release-please only proposes a release on each push
  to `main`, and nothing is tagged until a human merges the release PR. We merge one at
  milestones, not after every change.
- **Tokens:** it runs with a dedicated PAT so CI runs on release PRs (PRs opened with
  `GITHUB_TOKEN` trigger no workflows). The PAT can't merge.
- **Lockfiles are bumped with the version:** release-please's TOML updater edits the
  `uv.lock` and `Cargo.lock` entries, and CI runs `uv lock --check`.
- **Unreleased components start at `0.0.0`,** so the first `feat` releases `0.1.0`.
- **Build identity:** `scripts/version.sh` derives it from `git describe`.

## Alternatives
- **One repo-wide version:** rejected, because it couples the agent's and the app's release
  cadence.
- **semantic-release or changesets:** rejected. Both are npm-centric, and release-please
  handles Python and Rust files per path.
- **Releasing on every merge:** rejected, because nothing deploys yet (#37) and it would
  just create tag noise.

## Consequences
- Keep each commit within one component's path.
- Compatibility between agent and app versions has to be proven by the protocol version and
  an integration test in CI.

## Revisit when
Deploys start (#37 and #38), which may call for release bundles of matched agent and app
versions (#66).
