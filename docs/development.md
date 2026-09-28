# Develop

Everything runs in the devcontainer (Python, Node, Rust, Tauri, Docker via the host).
Open the repo in VS Code → **Reopen in Container**.

## The model stack (agent + local models)
```sh
docker compose up -d
```
Starts the agent plus Ollama (LLM, `qwen2.5:1.5b`) and speaches (Whisper STT, Piper TTS),
reachable on `jarvis-net` only. The first run pulls the images (~12 GB unpacked) and
~1.2 GB of models. CPU by default; for an NVIDIA GPU, uncomment the `deploy:` snippet in
`docker-compose.yml`. Which model fills each role: [models.md](models.md).
End-to-end check: `cd agent && uv run --frozen --extra test pytest -m models`.

## The app
```sh
corepack enable && pnpm install
pnpm --dir frontend dev          # in a browser: http://localhost:5173 (?demo=1 for the demo)
cd frontend && cargo tauri dev   # or the native window
```
Point the UI at another agent with `VITE_AGENT_WS_URL`; the URL must also be allowed by the
CSP in `tauri.conf.json` (see `frontend/.env.example`).

## Tests and checks
```sh
pnpm turbo run lint typecheck test build                 # frontend + packages
cd agent && uv run --frozen --extra test pytest -q        # agent
scripts/ci-local.sh                                       # CI locally (act)
IT_NETWORK=1 scripts/integration-test.sh                  # agent × app, in the devcontainer
```
pre-commit runs format and lint on commit, tests on push. How we work (commits, releases,
PRs): [AGENTS.md](../AGENTS.md).
