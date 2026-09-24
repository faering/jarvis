# 0005. Release artifacts and gated per-component Pi deploy
Status: Accepted · Date: 2026-09-24

## Context
Each component releases on its own (ADR 0004). A release has to turn into artifacts
(agent image, app bundle) and reach the Pi one component at a time, without shipping
broken code or a pair that can't talk to each other.

## Decision
- **Artifacts on `release: published`.** The agent becomes a multi-arch GHCR image tagged
  with `DOCKER_TAG`. The app becomes `.deb` bundles attached to the release. A
  `manifest.json` (version, revision, protocol) goes up last and marks the release complete.
- **CI gate.** Nothing builds unless the tagged commit's `ci-ok` check passed.
- **Deploy over plain `ssh`/`scp`** from a `pi` GitHub Environment, so approval is a
  required reviewer. The deploy scripts run on the Pi and roll back on failure.
- **Compatibility gate:** same WebSocket `PROTOCOL_VERSION`, overridable by the
  `known_good` and `blocked` lists in `compatibility.json`. The Pi records what it runs in
  `~/jarvis/state/`.

## Alternatives
- **Build artifacts on tag push:** rejected. release-please publishes the release, so the
  release event carries the tag and doesn't depend on how the tag was created.
- **Native arm64 runners for the image, merged by digest:** deferred. The image build only
  installs wheels, so QEMU is fast enough and uses one job. The app does use a native
  `ubuntu-24.04-arm` runner, because Rust under emulation is slow.
- **`tauri-action`:** not used. Our Linux-only build is one `pnpm tauri build` plus
  `gh release upload`, with no release-creation logic to fight.
- **`appleboy/ssh-action`:** not used. Plain `ssh` keeps the host key pinned via
  `PI_SSH_KNOWN_HOSTS` and lets scripts be piped as-is.
- **Hand-maintained protocol table per release:** rejected. The protocol is read from the
  source at the tag, so it can't drift.

## Consequences
- The Pi must be reachable from GitHub-hosted runners (a public endpoint or a VPN step).
- The app's `.deb` needs glibc 2.39 or newer (Pi OS Trixie).
- An app deploy only installs the package. The new version runs from the next start
  (supervisor #65).

## Revisit when
Release bundles (#66), blue/green (#64) or self-deploy (#38) land, or when the CI
integration test can replace the protocol-only gate.
