# shellcheck shell=bash
# Verify a release artifact's provenance offline (#121): it must carry a Sigstore-signed
# build-provenance attestation from this repo's release-artifacts workflow. Setup installs
# this root-owned as /usr/local/lib/jarvis/verify.sh; jarvis-install-app and
# jarvis-deploy-agent source it (only if root owns it) and fail closed without it.
#
# Offline: no GitHub token, no API call. gh checks the bundle against a trusted root that
# jarvis-attest-root.timer refreshes daily (scripts/lib/refresh-trusted-root).

JARVIS_ATTEST_REPO=faering/jarvis
JARVIS_ATTEST_WORKFLOW=faering/jarvis/.github/workflows/release-artifacts.yml

verify_artifact() { # verify_artifact <file> <bundle>: 0 = built by our release workflow
  local file="$1" bundle="$2" root="${JARVIS_TRUSTED_ROOT:-/var/lib/jarvis/attest/trusted_root.jsonl}"
  local gh="${JARVIS_GH:-/usr/bin/gh}" home rc
  if [[ ! -s "$root" ]]; then
    echo "verify: no trusted root at $root (sudo systemctl start jarvis-attest-root)" >&2
    return 1
  fi
  [[ -f "$file" && -f "$bundle" ]] || {
    echo "verify: missing artifact or bundle" >&2
    return 1
  }
  # A clean environment: no token, config or cache from whoever called us.
  home="$(mktemp -d)"
  env -i PATH=/usr/bin:/bin HOME="$home" "$gh" attestation verify "$file" \
    --bundle "$bundle" --custom-trusted-root "$root" \
    --repo "$JARVIS_ATTEST_REPO" --signer-workflow "$JARVIS_ATTEST_WORKFLOW" \
    --deny-self-hosted-runners >&2
  rc=$?
  rm -rf "$home"
  return "$rc"
}
