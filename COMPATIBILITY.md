# Compatibility

The agent and app release independently, so every deploy checks that the component being
rolled out can run next to the **other component's currently deployed release**.
`deploy.yml` runs [`scripts/deploy/check-compat.sh`](scripts/deploy/check-compat.sh) against
[`compatibility.json`](compatibility.json) and refuses an incompatible pair.

## Rule (first match wins)
1. The other component isn't deployed yet → OK.
2. The pair is in `blocked` → refused.
3. The pair is in `known_good` → OK.
4. Either side has no WebSocket protocol yet (`"none"`) → OK.
5. Both speak the same WebSocket `PROTOCOL_VERSION` → OK; otherwise refused.

Each release's protocol version is read from its source at the tag and recorded in the
release's `manifest.json` asset; the Pi records what it runs in `~/jarvis/state/*.env`.

## Maintaining `compatibility.json`
- **`known_good`**: add `{ "agent": "X.Y.Z", "app": "A.B.C" }` once a pair is verified on
  the Pi.
- **`blocked`**: add a pair that shares a protocol but is broken anyway.

Pairs use bare release versions (`1.2.3`). The integration test that should gate releases
(AGENTS.md) and bundle-level pinning (#66) are still to come; until then, the protocol
version is the contract.
