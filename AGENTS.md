# Jarvis — Agent & Engineering Instructions

Canonical, tool-agnostic instructions for any AI agent (and humans) working on Jarvis.
Keep it lean. Domain vocabulary lives in [CONTEXT.md](CONTEXT.md); per-language deep rules
live in `.claude/rules/` and load only when you touch matching files.

## Who you are
An **expert software engineer** on Jarvis. You own code quality, architecture fit, and
correctness — not just output. Expert in:
- **This stack:** Python (agent/API + tools), TypeScript/React (frontend), Rust (Tauri
  backend only), Docker/Compose, devcontainers, GitHub Actions, and the Raspberry Pi 5 /
  Hailo NPU / IMX500 hardware target.
- **This project:** the Jarvis architecture, decisions, and conventions below.

## How you behave (operating principles)
- **Ask when in doubt.** Don't assume or silently infer intent on anything ambiguous or
  consequential — ask a focused question first.
- **Don't know? Find out.** Fetch current, version-accurate info from the web or context7
  (see the `docs-lookup` skill) before answering. Never guess at version-specific behavior.
  If it's still unclear, say so plainly and ask — don't paper over uncertainty.
- **Respect the boundaries** below (language boundaries, Docker/Tauri split, Pi-only
  paths). Flag anything a task would force you to cross.
- **Be concise and coherent.** Short, direct, no clutter or filler. Answer what's asked;
  add only what's needed to be correct and actionable.
- **Uphold the standards** below in every change.

## Mission
Jarvis is a handheld, physically embodied AI companion (Iron-Man-inspired) that helps plan
the day, take notes, manage the calendar, and act as a sparring partner for hobby projects.

## Hardware & three-compute-layer routing
- Raspberry Pi 5 (16GB) orchestrator; AI HAT+ 2 (Hailo-10H NPU, 40 TOPS, 8GB); AI Camera
  (IMX500); USB mic + speaker; 4–5" touchscreen; 3D-printed enclosure.
- **Routing across three layers:** IMX500 on-camera inference → Hailo NPU → Pi 5 CPU
  orchestrator.
- The always-on voice loop uses small quantized models (1–4B class). Heavier tasks route
  **async** to the cloud or larger local models — never on the hot path.

## Language boundaries (do not cross)
- **Python** — agent/API layer and all tools.
- **TypeScript/React** — the frontend.
- **Rust** — strictly the Tauri backend. Never leaks into agent logic.

## Monorepo & runtime layout
- Everything except the display (agent, tools) lives in a **Docker Compose monorepo**.
- The display is a **native Tauri app, NOT in Docker**; it talks to the Docker stack over
  **WebSocket**.
- Compose services and the devcontainer share the external Docker network `jarvis-net`.
- **Speech output never blocks:** producer/consumer async queue with turn-boundary checks.

### Planned monorepo layout & JS/TS tooling
- **`agent/`** — Python (Docker). Not part of the JS workspace; orchestrated via Docker
  Compose + pytest.
- **`frontend/`** — the Tauri **app** (TS/React UI + Rust `src-tauri/`).
- **JS/TS side is a pnpm workspace**, bundled with **Vite** (Tauri's default). **Turborepo**
  is adopted **together with the frontend skeleton** (backlog f4.1) — not before, since
  there's no JS to orchestrate until then; its caching/task-graph pays off as packages grow.
- **Anticipated `packages/*`** (drive the workspace design): `protocol` (TS types/schema for
  the agent↔app WebSocket contract), `ui` (shared React components), `config` (shared
  eslint/tsconfig/prettier). See backlog f4.4.
- Work happens in the devcontainer (Python 3.14, Node 24 LTS, Rust, Tauri), with
  docker-outside-of-docker so `docker compose up` targets the agent stack. Toolchains are
  pinned to latest stable and bumped deliberately.
- **The hardware inference path (Hailo SDK, IMX500 camera, GPIO) runs only on the Pi** — it
  is not part of the devcontainer, which is for agent/API/UI code, tests, and CI.

## Standards (enforced from commit #1)
- **pre-commit**: format + lint on the `pre-commit` stage, tests on `pre-push`.
- **Conventional Commits** via commitizen on the `commit-msg` stage. Use `cz commit`.
  commitizen lints messages only — it does **not** bump versions.
- **Releases**: automated by **release-please** — see *Releases & commit conventions*.
- Run CI locally with **`act`** (`scripts/ci-local.sh`) before pushing.

## Releases & commit conventions (read before every commit)
Jarvis releases **independently per component** — the two deployable units version and tag
on their own cadence, so we can ship a stable app and keep iterating the agent:
- **agent** — Python agent/API + tools (Docker image) → tag `agent-vX.Y.Z`, path `agent/`.
- **app** — Tauri binary (TS/React + Rust `src-tauri/`, released together) → tag
  `app-vX.Y.Z`, path `frontend/`.

**How release-please decides what to release — by the files a commit touches, NOT the
scope.** So:
- **Keep each commit within ONE component's path** (`agent/**` or `frontend/**`). A commit
  touching both bumps both. Repo/infra files (`.devcontainer/`, `.github/`, root config)
  are outside both paths → they trigger **no** release (correct).
- **Type drives the bump** (SemVer): `feat:` → minor, `fix:`/`perf:` → patch,
  `feat!:`/`fix!:` or a `BREAKING CHANGE:` footer → major. `docs/refactor/test/ci` show in
  the changelog but don't bump; `chore` is hidden.
- **Scope = the component, for readability** (routing is still path-based):
  `feat(agent): …`, `fix(app): …`, `chore(repo): …` for cross-cutting infra.
- commitizen (`cz commit`, commit-msg hook) enforces the format; it never bumps versions.
- release-please opens **one release PR per component**; merging it tags + writes that
  component's `CHANGELOG.md` + cuts the GitHub release.
- **Dormant until scaffolded:** the workflow is `workflow_dispatch`-only until `agent/` and
  `frontend/` exist (missing package files fail validation). Flip it to `push: main` when
  the skeleton lands (backlog f3.1 / f4.1).

**Linking commits & PRs to their work-item issue** (GitHub is strict — these are the traps):
- **A closing keyword is required.** Recognized: `close/closes/closed`, `fix/fixes/fixed`,
  `resolve/resolves/resolved`. A **bare `#12` only mentions/links — it does NOT close.**
- **Repeat the keyword before every issue:** `Closes #1, closes #2`. `Closes #1, #2` closes
  only #1.
- **Only the default branch closes.** A keyword in a **commit message** closes the issue when
  the commit lands on `main`; on a feature branch it is ignored until merged. In a **PR
  description** the issue auto-closes when the PR merges into `main` (and shows as a linked PR).
- **Squash-merge drops commit-message footers** — so when merging via a PR, put every
  `Closes #n` in the **PR description**, not only in the commits.
- Use `Refs #n` (no keyword) to link without closing; cross-repo (rare here) is
  `Closes owner/repo#100`.

**Cross-component compatibility (actively maintain this):** independent versions mean
agent `vX` and app `vY` must be proven to work together.
- The agent↔app **WebSocket contract is the single source of truth for compatibility**;
  keep it in a versioned protocol schema shared by both sides and bump it deliberately.
- CI must run an **integration test** (agent stack up + app client exercised against it)
  and it gates every component release.
- Record last-known-good combinations (a `COMPATIBILITY.md` / device manifest) and have the
  **deploy workflow ship a matched set** to the Pi.
- When releasing one component, run the integration suite against the **currently released**
  version of the other before deploying.

### Build provenance & displayed versions
Every version shown anywhere must answer: *which tag is this build on, how many commits
ahead, and is the tree dirty?* Derived at build time from
`git describe --tags --match '<component>-v*' --long --always --dirty`, then reduced to a
bare `MAJOR.MINOR.PATCH` (strip the `<component>-v` prefix). Because a **Docker tag cannot
contain `+`**, the same build has two forms — sanitized only where required:

- **Canonical (strict SemVer)** — app UI, agent `/version`, and the OCI
  `org.opencontainers.image.version` label (all allow `+`):
  - release (clean tag): `1.2.3`
  - dev: `1.2.3+<ahead>.g<sha>` (dirty → `1.2.3+<ahead>.g<sha>.dirty`)
- **Docker image tag** (no `+`) — git-describe form:
  - release: `1.2.3` · dev: `1.2.3-<ahead>-g<sha>` (dirty → `1.2.3-<ahead>-g<sha>-dirty`)
- **`org.opencontainers.image.revision`** = the full commit sha.

Compute once via `scripts/version.sh <component>` (emits both `CANONICAL` and `DOCKER_TAG`);
feed `CANONICAL` to Vite (`VITE_APP_VERSION`) + the agent, and `DOCKER_TAG` to
`docker build -t`. Agent and app then display the identical canonical value.
No `<component>-v*` tag yet → base `0.0.0`, ahead = total commit count
(`0.0.0+<count>.g<sha>`). CI checkouts need `fetch-depth: 0`, or there are no tags.

## CI/CD
- GitHub Actions → SSH deploy to the Pi (deploys a **matched** agent+app set; see above).
- Stretch goal: Jarvis self-deploys on new-release detection, human in the loop.

## Work-item workflow
- Work items live in **GitHub** (source of truth), mirrored locally in `github-issues.json`.
  Full Agile hierarchy: Epic → Feature → Story → Task, plus Bug.
- Type/priority/status are modeled with labels (native Issue Types are org-only); a GitHub
  **Project (v2)** board mirrors them as fields; hierarchy uses a `parent` field.
- Canonical shape & sync semantics: [`.claude/skills/_shared/issue-schema.md`](.claude/skills/_shared/issue-schema.md).
- Skills: `new-issue`, `plan-issue`, `open-pr` (authoring); `wi-fetch`, `wi-push`,
  `wi-sync` (mirror sync with 3-way-merge conflict resolution); `docs-lookup` (current
  docs via context7 before answering library/API questions).
