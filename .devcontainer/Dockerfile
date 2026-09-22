# Jarvis dev container
# Toolchains for the agent/API/UI code, tests, and CI.
# NOTE: the on-device inference path (Hailo SDK, IMX500 camera, GPIO) is Pi-only
# and is intentionally NOT installed here.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Pinned to the latest stable at time of writing. Bump deliberately; keep in step
# with the "toolchain latest-version policy" (backlog E1).
ARG PYTHON_VERSION=3.14
ARG NODE_VERSION=24
ARG RUST_VERSION=1.98.1
ARG UV_VERSION=0.12.15
ARG ACT_VERSION=0.2.89

ENV DEBIAN_FRONTEND=noninteractive

# ---- System deps -----------------------------------------------------------
# build-essential/pkg-config/openssl: Rust + native builds.
# libwebkit2gtk/gtk/appindicator/rsvg: Tauri Linux runtime + build deps.
# Python itself is NOT installed via apt — Ubuntu 24.04 only ships 3.12; we use
# uv to install and manage the pinned Python instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libssl-dev \
        curl \
        wget \
        file \
        git \
        ca-certificates \
        libwebkit2gtk-4.1-dev \
        libgtk-3-dev \
        libayatana-appindicator3-dev \
        librsvg2-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Node (via nodesource) -------------------------------------------------
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable

# ---- act (run GitHub Actions locally) -------------------------------------
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
        amd64) act_arch="x86_64" ;; \
        arm64) act_arch="arm64" ;; \
        *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/nektos/act/releases/download/v${ACT_VERSION}/act_Linux_${act_arch}.tar.gz" \
        -o /tmp/act.tar.gz; \
    tar -xzf /tmp/act.tar.gz -C /usr/local/bin act; \
    rm /tmp/act.tar.gz; \
    act --version

# ---- GitHub CLI (official apt repo) ---------------------------------------
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/* \
    && gh --version

# ---- System-wide git quality-of-life (survives without persisting $HOME) ---
# git log is newest-first + scrollable by default; pager tweak avoids trapping
# short output. show-dirty adds the base prompt's dirty marker. User identity is
# supplied by the read-only ~/.gitconfig bind mount (see devcontainer.json).
# SSH commit signing is set here rather than in ~/.gitconfig: that file is a
# single-file bind mount, and `git config` replaces it (write-temp + rename), so
# host edits land on a new inode the running container never sees. Signing uses
# the mounted key via the forwarded SSH agent.
RUN git config --system init.defaultBranch main \
    && git config --system pull.ff only \
    && git config --system push.autoSetupRemote true \
    && git config --system core.pager 'less -FRX' \
    && git config --system log.date iso \
    && git config --system devcontainers-theme.show-dirty 1 \
    && git config --system gpg.format ssh \
    && git config --system user.signingkey /home/vscode/.ssh/id_ed25519.pub \
    && git config --system commit.gpgsign true \
    && git config --system tag.gpgsign true \
    git config --system gpg.format ssh \
    && git config --system user.signingkey /home/vscode/.ssh/id_ed25519.pub \
    && git config --system commit.gpgsign true \
    && git config --system tag.gpgsign true

# ---- Everything below runs as the non-root devcontainer user --------------
USER vscode
ENV HOME=/home/vscode
# .venv gives a default `python` on PATH; .cargo for Rust; .local for uv + uv tools.
ENV PATH="${HOME}/.venv/bin:${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

# uv: fast Python package/toolchain manager (pinned).
RUN curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh

# Managed Python (pinned) exposed as the default `python`/`python3` via a venv.
RUN uv python install "${PYTHON_VERSION}" \
    && uv venv --python "${PYTHON_VERSION}" "${HOME}/.venv"

# Python developer tooling (isolated CLI installs via uv tool).
RUN uv tool install pre-commit \
    && uv tool install commitizen \
    && uv tool install ruff

# Rust (pinned) + Tauri CLI.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain "${RUST_VERSION}" --profile minimal \
    && rustup component add rustfmt clippy \
    && cargo install tauri-cli --locked

# gh reads GH_TOKEN/GITHUB_TOKEN. If neither is present, fall back to GITHUB_PAT
# so gh still works in local dev. git-over-SSH uses the mounted ~/.ssh keys.
RUN printf '\n# gh auth falls back to GITHUB_PAT\nexport GH_TOKEN="${GH_TOKEN:-$GITHUB_PAT}"\n' \
    >> "${HOME}/.bashrc"

# Sanity: tools resolve on PATH for interactive shells.
RUN python --version && node --version && cargo --version \
    && pre-commit --version && cz version && act --version && gh --version
