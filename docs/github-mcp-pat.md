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

## 2) Tool allowlist (least privilege)
`.mcp.json` loads **only the tools the skills use** (`X-MCP-Tools`), not whole toolsets.
Adding a tool is a deliberate change to that list.

| Group | Tools | Used by |
|-------|-------|---------|
| Context | `get_me` | start-issue |
| Issues | `issue_read`, `issue_write`, `list_issues`, `search_issues`, `sub_issue_write`, `add_issue_comment`, `get_label` | new-issue, plan-issue, wi-* |
| Pull requests | `create_pull_request`, `pull_request_read`, `update_pull_request`, `list_pull_requests`, `search_pull_requests`, `add_reply_to_pull_request_comment` | open-pr, review follow-up |
| Projects | `projects_get`, `projects_list`, `projects_write` | board-sync, start-issue |
| Repo (read-only) | `get_file_contents`, `list_commits`, `get_commit`, `list_branches`, `list_tags`, `list_releases`, `get_latest_release` | lookups |

**Never available to the agent.** These are listed in `X-MCP-Exclude-Tools`, which
overrides any allowlist, and also blocked by deny rules in `.claude/settings.json`:
- `delete_repository`, `create_repository`, `fork_repository`
- `merge_pull_request`, `update_pull_request_branch`: merging stays the human gate (`gh pr merge` is denied too)
- `delete_file`, `create_or_update_file`, `push_files`: files change only through local
  git commits, so the pre-commit hooks always run

Changes to `.mcp.json` take effect after restarting the Claude Code session.

## 3) Permissions (minimum for Jarvis MCP skills)
Set these permissions on the PAT:
- Repository permissions:
  - Metadata: Read
  - Contents: Read (the MCP no longer writes files; pushes go through git)
  - Issues: Read and Write
  - Pull requests: Read and Write
- Organization permissions (if org Projects are used):
  - Projects: Read and Write

Optional, only if needed by your workflow:
- Organization members: Read (for assignee/member lookups)

## 4) SSO
If your org uses SAML SSO, authorize the token for that org after creation.

## 5) Put token in devcontainer env
Edit .devcontainer/devcontainer.env:

```env
# Dedicated token for local dev MCP agent actions
GITHUB_PAT=github_pat_xxx
```

Why: .mcp.json reads GITHUB_PAT for MCP auth.

## 6) Forward gh token from WSL (optional, recommended)
1. In WSL shell, set your gh token once in your shell profile:

```bash
export GITHUB_TOKEN="$(gh auth token)"
```

2. Reopen/rebuild the devcontainer.

Result: devcontainer forwards WSL GITHUB_TOKEN to container GH_TOKEN/GITHUB_TOKEN.
If unset, gh falls back to GITHUB_PAT.

## 7) Rebuild and verify
1. Rebuild/reopen the devcontainer.
2. Verify MCP auth by running an agent skill that hits GitHub.
3. Verify gh auth:
   - gh auth status

## 8) Troubleshooting
- 403 on Projects calls: token likely missing org Projects permission, wrong owner, or not SSO-authorized.
- Repos visible but writes fail: Contents/Issues/PR permissions are Read only.
- Need user-owned Projects: fine-grained PAT does not support this; use classic PAT or GitHub App for that case.
