# release-please token

The release-please workflow needs its own token. If it opens release PRs with the
default `GITHUB_TOKEN`, GitHub doesn't start any other workflows for them, so CI and
the required `ci-ok` check never run and the ruleset blocks the merge.

## Create it (once)
1. Go to https://github.com/settings/personal-access-tokens/new and create a
   **fine-grained** PAT.
2. **Repository access:** only `faering/jarvis`.
3. **Permissions:**
   - Contents: Read and write (release commits, tags, releases)
   - Pull requests: Read and write (open and update the release PR)
   - Issues: Read and write (the `autorelease: pending` / `tagged` labels on release PRs)
   - Metadata: Read (set automatically)
4. **Expiration:** 90 days. Set a reminder to rotate it.
5. Add it as a repo secret named **`RELEASE_PLEASE_TOKEN`**:
   `gh secret set RELEASE_PLEASE_TOKEN --repo faering/jarvis` (paste the token when
   prompted), or add it under Settings → Secrets and variables → Actions.

If the secret is missing, the workflow fails with a clear error. It never falls back to
`GITHUB_TOKEN`, because that fallback would produce release PRs that can't be merged.

## What it can do
The token can open and update release PRs and create tags and releases. **It never
merges anything:** a release is cut only when a human merges the release PR.
