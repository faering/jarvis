# GitHub MCP PAT Setup (Local Dev Agent)

## Goal
Use a dedicated PAT for local development agent MCP skills in this repo.

## Scope
- In scope: local Copilot/Claude agent actions via GitHub MCP while developing Jarvis.
- Out of scope: live Jarvis runtime credentials and production deployment auth.

## 1) Create the PAT
1. Open: https://github.com/settings/personal-access-tokens/new
2. Token type: Fine-grained personal access token.
3. Resource owner: the org that owns the Jarvis repos and Projects.
4. Repository access: only the repos Jarvis should manage.
5. Expiration: short (30-90 days) and rotate.

## 2) Permissions (minimum for Jarvis MCP skills)
Jarvis GitHub MCP uses toolsets: context, repos, issues, pull_requests, projects.

Set these permissions on the PAT:
- Repository permissions:
  - Metadata: Read
  - Contents: Read and Write
  - Issues: Read and Write
  - Pull requests: Read and Write
- Organization permissions (if org Projects are used):
  - Projects: Read and Write

Optional, only if needed by your workflow:
- Organization members: Read (for assignee/member lookups)

## 3) SSO
If your org uses SAML SSO, authorize the token for that org after creation.

## 4) Put token in devcontainer env
Edit .devcontainer/devcontainer.env:

```env
# Dedicated token for local dev MCP agent actions
GITHUB_PAT=github_pat_xxx
```

Why: .mcp.json reads GITHUB_PAT for MCP auth.

## 5) Forward gh token from WSL (optional, recommended)
1. In WSL shell, set your gh token once in your shell profile:

```bash
export GITHUB_TOKEN="$(gh auth token)"
```

2. Reopen/rebuild the devcontainer.

Result: devcontainer forwards WSL GITHUB_TOKEN to container GH_TOKEN/GITHUB_TOKEN.
If unset, gh falls back to GITHUB_PAT.

## 6) Rebuild and verify
1. Rebuild/reopen the devcontainer.
2. Verify MCP auth by running an agent skill that hits GitHub.
3. Verify gh auth:
   - gh auth status

## 7) Troubleshooting
- 403 on Projects calls: token likely missing org Projects permission, wrong owner, or not SSO-authorized.
- Repos visible but writes fail: Contents/Issues/PR permissions are Read only.
- Need user-owned Projects: fine-grained PAT does not support this; use classic PAT or GitHub App for that case.
