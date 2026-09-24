# Pi first-time setup

Do this once on a fresh Pi to make it deployable from GitHub (`.github/workflows/deploy.yml`). Replace `<user>` with your Pi user
and `<pi>` with the Pi's Tailscale name (step 2).

## Why Tailscale
GitHub runs deploys on its own servers, so they can't reach `jarvis.local` or a home/office IP
(both only work on your local network, and IPs change between Wi-Fi networks). Tailscale gives
the Pi one fixed name, e.g. `jarvis.tail1234.ts.net`, that works on any network. The deploy job
joins your tailnet for a few minutes (step 3) and SSHes to that name.

## 1. Prepare the Pi
Raspberry Pi OS **64-bit, Trixie or newer**. Then, on the Pi:
```sh
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker "$USER"   # Docker + Compose v2
echo "$USER ALL=(root) NOPASSWD: /usr/bin/apt-get" | sudo tee /etc/sudoers.d/jarvis-deploy
sudo chmod 440 /etc/sudoers.d/jarvis-deploy   # the app deploy installs its .deb with apt-get
mkdir -p ~/jarvis && touch ~/jarvis/.env      # runtime config (see .env.example)
```
Log out and in again so the `docker` group applies.

## 2. Put the Pi on Tailscale
1. Create a free account at [tailscale.com](https://tailscale.com). Install Tailscale on your
   work/dev PC too.
2. Admin console → **DNS**: make sure **MagicDNS** is enabled (it is on new tailnets). The
   `*.ts.net` names below depend on it.
3. Admin console → **Access controls**: add two tags. Let your own devices reach the Pi, and
   let CI reach it on SSH only. (With the default allow-all policy, `grants` is optional.)
   ```json
   "tagOwners": { "tag:ci": ["autogroup:admin"], "tag:jarvis": ["autogroup:admin"] },
   "grants": [
     { "src": ["autogroup:member"], "dst": ["tag:jarvis"], "ip": ["*"] },
     { "src": ["tag:ci"], "dst": ["tag:jarvis"], "ip": ["tcp:22"] }
   ]
   ```
4. On the Pi: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --advertise-tags=tag:jarvis`,
   then open the printed link to add it. Tagged devices don't expire, so the Pi stays reachable.
5. Its full name in the admin console (`<name>.<tailnet>.ts.net`) is `<pi>` in the steps
   below. Check from your PC: `ssh <user>@<pi>`.

## 3. Let GitHub join the tailnet
Admin console → **Settings → Trust credentials** → new OAuth client with the **Auth Keys:
Write** scope and tag `tag:ci` (defined in step 2). Keep the client ID and secret for step 5;
they go in as a pair.

## 4. Deploy key and host key
On your PC (on the tailnet):
```sh
ssh-keygen -t ed25519 -f jarvis-deploy -N "" -C github-deploy   # key pair only for deploys
ssh-copy-id -i jarvis-deploy.pub <user>@<pi>
ssh-keyscan -t ed25519 <pi> > known_hosts                       # the Pi's host key
ssh-keygen -lf known_hosts   # must match `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the Pi
```

## 5. Create the GitHub environment
Repo **Settings → Environments → New environment** `pi`:
- **Required reviewers:** you. Every rollout then waits for your approval.
- **Environment secrets:**

  | Secret | Value |
  |---|---|
  | `PI_SSH_HOST` | `<pi>`: the full Tailscale name, not an IP |
  | `PI_SSH_USER` | `<user>` |
  | `PI_SSH_KEY` | contents of `jarvis-deploy` (the private key) |
  | `PI_SSH_KNOWN_HOSTS` | contents of `known_hosts` |
  | `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` | the OAuth client from step 3 |

Then **Settings → Secrets and variables → Actions → Variables**: `PI_DEPLOY_ENABLED` = `true`.

## 6. Container image access
After the first `agent-v*` release, open the `jarvis-agent` package on GitHub → **Package
settings** → make it **Public**. Or run `docker login ghcr.io` on the Pi with a PAT that has
`read:packages`.

## 7. Test
**Actions → deploy → Run workflow**, pick `agent` and a released version, and approve it.
The log shows the tailnet join, the compatibility check and the health check.

## Moving the Pi (home ↔ office)
Nothing changes in GitHub: the Tailscale name follows the Pi. The Pi only needs internet on
the new Wi-Fi. Add that network on the Pi first (`sudo nmtui`). Captive-portal networks won't
work; company WPA2-Enterprise networks may need IT's details.

## Reaching the Pi yourself
- **[Raspberry Pi Connect](https://connect.raspberrypi.com)**: a browser shell or screen share
  from any computer, over any network. Good for a quick look; it isn't used by deploys.
- **Tailscale**: `ssh <user>@<pi>` or VS Code Remote-SSH from any PC on your tailnet, on any
  network.
