#!/usr/bin/env bash
# Runs once after the container is created. Idempotent.
set -euo pipefail

# Named volumes are created root-owned; hand them to the devcontainer user so
# Claude Code and shell history can write to them. ~/.npm and ~/.cache can also end
# up root-owned from the image build, which breaks pre-commit's node-based hooks.
sudo chown -R vscode:vscode \
  /home/vscode/.claude /commandhistory \
  "$HOME/.npm" "$HOME/.cache" 2>/dev/null || true
touch /commandhistory/.bash_history 2>/dev/null || true

# Install git hooks for every stage the project uses. Safe to re-run.
if [ -f .pre-commit-config.yaml ]; then
  # Install hooks for every stage. Hook versions are pinned in the config and bumped
  # deliberately in a PR (no autoupdate here: it left unstaged edits that abort commits).
  pre-commit install \
    --hook-type pre-commit \
    --hook-type pre-push \
    --hook-type commit-msg
fi

echo "Jarvis dev container ready."
