# 0009. Least-privilege Pi deploys
Status: Accepted. Date: 2026-09-27.

## Context
ADR 0006 deploys over SSH. The deploy user ran `docker compose` itself, so it had to be in
the `docker` group, which is root-equivalent (a container can mount `/`). It also uploaded
the compose file, and whoever controls that file controls the mounts. A stolen
`PI_SSH_KEY` meant a Pi takeover (#131).

## Decision
- The deploy key logs in as `deploy`, **not** in the `docker` group.
- Root actions go through two audited, root-owned scripts, and sudoers allows only them:
  `jarvis-deploy-agent` (agent) and `jarvis-install-app` (app `.deb`, from #115).
- `jarvis-deploy-agent` takes only a `DOCKER_TAG`-shaped tag that matches the expected
  version, pulls only `ghcr.io/faering/jarvis-agent`, and runs the root-owned
  `/opt/jarvis/docker-compose.yml`. It refuses a compose file or directory that isn't
  root-owned or is group/world-writable. Health, version checks and rollback are as before.
- Agent state and runtime config move to root-owned `/var/lib/jarvis/` and
  `/opt/jarvis/agent.env`. The compat gate reads the state through `jarvis-deploy-agent state`.
- deploy.yml refuses a deploy user in the `docker` group.

## Alternatives
- **Keep the `docker` group:** rejected; the key stays root-equivalent.
- **Rootless Docker for the deploy user:** rejected for now. More moving parts on the Pi
  (user systemd, networking, later device access for the Hailo/camera), and the deploy user
  would still control the agent's containers and mounts.
- **A deploy daemon or pull-based agent on the Pi:** rejected for now. A new long-running
  privileged service to build and secure; the self-deploy goal (#38) may revisit it.

## Consequences
- A stolen deploy key can still roll the agent to any **published** image tag and install
  any `jarvis` `.deb` it stages. Verifying provenance on the Pi is #121.
- Changing the root scripts or the compose file needs an admin to re-run the Pi setup;
  merging to `main` no longer changes what runs as root on the Pi.
- A private GHCR package needs `sudo docker login ghcr.io` (root pulls).

## Revisit when
Provenance verification (#121) or self-deploy (#38) lands.
