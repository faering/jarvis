# Pi first-time setup

`scripts/pi/setup.sh` sets up and hardens the Pi; this guide covers only what a script can't
do (accounts, keys, secrets). `<user>` is your Pi login, `<pi>` the Pi's Tailscale name.

**Why Tailscale:** GitHub's runners can't reach `jarvis.local` or a home/office IP. Tailscale
gives the Pi one fixed name (e.g. `jarvis.tail1234.ts.net`) on any network; the deploy job
joins your tailnet for a few minutes and SSHes to it. SSH is only open over Tailscale.

## 1. Tailscale account
1. Create a free account at [tailscale.com](https://tailscale.com) and install Tailscale on
   your PC. Admin console → **DNS**: keep **MagicDNS** on.
2. Admin console → **Access controls**: add the tags, let **only you** reach the Pi and CI
   reach SSH only (`you@github` = your login, top right). Do this before step 3: the Pi
   joins with `tag:jarvis`.
   ```json
   "tagOwners": { "tag:ci": ["autogroup:admin"], "tag:jarvis": ["autogroup:admin"] },
   "grants": [
     { "src": ["you@github"], "dst": ["tag:jarvis"], "ip": ["*"] },
     { "src": ["tag:ci"], "dst": ["tag:jarvis"], "ip": ["tcp:22"] }
   ]
   ```

## 2. Flash the Pi
Raspberry Pi Imager: **Raspberry Pi OS 64-bit (Trixie or newer)**. In OS customisation set
your user and Wi-Fi, and under Services **enable SSH with public-key authentication** (paste
your PC's public key). The script refuses key-only SSH until your login has a key.

## 3. Run the setup script
On the Pi (keyboard or `ssh <user>@<pi-lan-ip>`):
```sh
git clone https://github.com/faering/jarvis.git ~/src/jarvis && cd ~/src/jarvis
sudo scripts/pi/setup.sh          # prints a Tailscale login link on the first run: open it
```
It installs Docker, Tailscale, nftables and unattended-upgrades; creates the `deploy` user
and root-owned deploy scripts, `/opt/jarvis/` and sudoers; hardens SSH; turns on the
firewall; sets up the journal, shell history and updates; and creates the log folder
`/var/log/jarvis` (group `jarvis-log`, GID 2750, which your login joins), `jarvis-logs` and
its hourly prune timer ([logging](logging.md)); and `gh` with a daily-refreshed Sigstore
trusted root, so every release is verified offline before it's installed (#121); and keeps
the Wi-Fi up: power saving off, reconnecting forever, never giving up on the password, and
Raspberry Pi's Wi-Fi driver workarounds checked (#206, #212). Details are in the script.
- Exit **3** = steps it deferred to keep you from being locked out (no SSH key yet,
  Tailscale not up). It prints why; fix that and re-run.
- **Re-run any time** (e.g. after `git pull`); `--check` reports drift and changes nothing.
- **Log out and back in** after the first run: a login only gets the new `jarvis-log` group
  at a fresh login. Until then `jarvis-logs` can't read the logs (it says so).
- After step 3, LAN SSH is closed: use `ssh <user>@<pi>`. The keyboard and screen always work.

Check from your PC: `ssh <user>@<pi>`. The full name is in the admin console.

## 4. Deploy key and host key
On your PC:
```sh
ssh-keygen -t ed25519 -f jarvis-deploy -N "" -C github-deploy   # key pair only for deploys
scp jarvis-deploy.pub <user>@<pi>:
ssh -t <user>@<pi> 'cd ~/src/jarvis && sudo scripts/pi/setup.sh --deploy-key ~/jarvis-deploy.pub'
ssh-keyscan -t ed25519 <pi> > known_hosts                       # the Pi's host key
ssh-keygen -lf known_hosts   # must match `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the Pi
```
The key goes to root-owned `/etc/ssh/authorized_keys/deploy`, marked `restrict` (no
forwarding, no terminal). `deploy` is not in the `docker` group; sudo lets it run only
`jarvis-deploy-agent` and `jarvis-install-app`.

## 5. Let GitHub join the tailnet
Admin console → **Settings → Trust credentials** → new OAuth client with the **Auth Keys:
Write** scope and tag `tag:ci`. Keep the client ID and secret for step 6.

## 6. GitHub environment
Repo **Settings → Environments → New environment** `pi`, **Required reviewers:** you, and
these **environment secrets**:

| Secret | Value |
|---|---|
| `PI_SSH_HOST` | `<pi>`: the full Tailscale name, not an IP |
| `PI_SSH_USER` | `deploy` |
| `PI_SSH_KEY` | contents of `jarvis-deploy` (the private key) |
| `PI_SSH_KNOWN_HOSTS` | contents of `known_hosts` |
| `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` | the OAuth client from step 5 |

Then **Settings → Secrets and variables → Actions → Variables**: `PI_DEPLOY_ENABLED` = `true`.

## 7. Image access and test
After the first `agent-v*` release, make the `jarvis-agent` package **Public** (package
settings), or on the Pi `sudo docker login ghcr.io` with a `read:packages` PAT. Then
**Actions → deploy → Run workflow**, pick `agent` and a version, and approve it.

## Day to day
- **Shell:** the prompt shows the git branch (`✗` = uncommitted changes), like the
  devcontainer; `ll` is `ls -la`; `vim` is the editor. Open a new terminal after setup.
- **Agent config** (API keys, `JARVIS_*`, as in `.env.example`): `sudoedit /opt/jarvis/agent.env`.
- **Logs:** Jarvis's own logs are in `/var/log/jarvis` (90 days, 20 GiB); read them with
  `jarvis-logs` ([logging](logging.md)): `jarvis-logs --since 1h`, `jarvis-logs -f`,
  `jarvis-logs --turn <id>`, `jarvis-logs usage`. Pruning: `systemctl list-timers
  jarvis-logs-prune.timer`, `journalctl -u jarvis-logs-prune`. Reading needs the
  `jarvis-log` group: log in again after the first setup run.
- **System logs** (journald, kept on disk, 500 MB / 1 month): `journalctl CONTAINER_NAME=jarvis-agent-1 -f`,
  `journalctl -u docker`, last boot `journalctl -b -1`.
- **Updates:** Debian, Pi and Tailscale updates install daily. If one needs a reboot
  (kernel, libc), the Pi reboots at 04:00. Docker updates are manual: `sudo apt upgrade`.
- **The Jarvis app** starts full screen at login once it has been deployed (autostart in
  `/etc/xdg/autostart/jarvis.desktop`). Minimize it with Ctrl+M or by asking Jarvis
  ("minimize"), and bring it back from the taskbar. Close it with Alt+F4; start it again
  from the menu (windowed) or with `jarvis-app --fullscreen`.
- **Bluetooth keyboard:** run `bluetoothctl`, then `power on`, `agent on`, `default-agent`,
  `scan on`; put the keyboard in pairing mode, then `pair <MAC>` (type the PIN shown on the
  keyboard + Enter), `trust <MAC>` (reconnects after reboots), `connect <MAC>`, `quit`.
  If it's blocked: `sudo rfkill unblock bluetooth`.
- **Moving networks:** nothing changes in GitHub. Add the new Wi-Fi first (`sudo nmtui`).
  Captive portals won't work; WPA2-Enterprise may need IT's details.
- **Wi-Fi watchdog:** about once a minute it pings the router. After 2 misses in a row it
  reconnects the Wi-Fi, then restarts NetworkManager, then reloads the Wi-Fi driver, then
  reboots (at most once an hour; a step that hangs reboots at once) (#207, #212). Check it
  with `systemctl list-timers jarvis-netwatch.timer` and `jarvis-logs --component system`;
  `fixed_by=` says which step brought it back.
- **Browser:** Chromium uses no keyring (autologin can't unlock one) and saves no passwords
  (#211). Logins in it are only lightly protected on the SD card: don't stay logged in to
  anything sensitive there.
- **Reaching the Pi:** `ssh <user>@<pi>` or VS Code Remote-SSH from your tailnet, or
  [Raspberry Pi Connect](https://connect.raspberrypi.com) in a browser (not used by deploys).
