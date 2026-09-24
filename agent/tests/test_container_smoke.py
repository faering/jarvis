"""Container integration smoke test (marker: ``container``).

Unlike test_smoke.py, which drives the in-process ASGI app, this builds and runs the real
image from docker-compose.yml and talks to it over the network. It catches a broken CMD,
a HEALTHCHECK that never turns healthy, or a port/jarvis-net misconfiguration. The image
is built with the real build provenance from scripts/version.sh, as scripts/compose-build.sh
does, and GET /version, the hello frame and the OCI labels must all report it.

Opt-in (excluded by default, so the pre-push hook stays fast); CI runs it explicitly:
    uv run --frozen --extra test pytest -m container

``AGENT_URL`` sets where the container is reached (default ``http://127.0.0.1:8000``, the
host port). Inside the devcontainer, 127.0.0.1 is the devcontainer itself, so use the
shared network instead: ``AGENT_URL=http://agent:8000``.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from websockets.sync.client import ClientConnection, connect


def _compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0


pytestmark = [
    pytest.mark.container,
    pytest.mark.skipif(not _compose_available(), reason="docker compose not available"),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
IMAGE = "jarvis-agent:dev"
NETWORK = "jarvis-net"
PROJECT = "jarvis-agent-smoke"
BASE_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8000").rstrip("/")
WAIT_TIMEOUT_S = "60"
BUILD_TIME = "2026-01-01T00:00:00Z"  # fixed, so the test can assert it


def _run(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"$ {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result.stdout


@pytest.fixture(scope="module")
def provenance() -> dict[str, str]:
    """KEY=VALUE output of ``scripts/version.sh agent`` (CANONICAL, DOCKER_TAG, REVISION)."""
    out = _run(str(REPO_ROOT / "scripts" / "version.sh"), "agent")
    return dict(line.split("=", 1) for line in out.splitlines())


@pytest.fixture(scope="module")
def running_container(provenance: dict[str, str]) -> Iterator[None]:
    # Build with the real provenance, as scripts/compose-build.sh does: compose reads these
    # for the agent's build args. Restored afterwards.
    build_env = {
        "JARVIS_VERSION": provenance["CANONICAL"],
        "JARVIS_REVISION": provenance["REVISION"],
        "JARVIS_BUILD_TIME": BUILD_TIME,
    }
    saved = {key: os.environ.get(key) for key in build_env}
    os.environ.update(build_env)

    # jarvis-net normally comes from the devcontainer's initializeCommand; create it if
    # missing (CI) and remove it again afterwards.
    created_network = (
        subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True).returncode
        != 0
    )
    if created_network:
        _run("docker", "network", "create", NETWORK)

    compose = ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT]
    try:
        # Only the agent: the model services are heavy and the agent must start without them.
        _run(
            *compose,
            "up",
            "--build",
            "--detach",
            "--wait",
            "--wait-timeout",
            WAIT_TIMEOUT_S,
            "agent",
        )
        yield
    finally:
        subprocess.run([*compose, "down", "--volumes"], capture_output=True)
        if created_network:
            subprocess.run(["docker", "network", "rm", NETWORK], capture_output=True)
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_health_endpoint(running_container: None) -> None:
    response = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Frames the agent pushes on its own (the initial state after hello, voice loop events);
# a test waiting for the answer to its request skips them.
EVENT_TYPES = {"state", "transcript", "reply"}


def _recv_answer(ws: ClientConnection) -> dict[str, object]:
    while (frame := json.loads(ws.recv(timeout=5)))["type"] in EVENT_TYPES:
        pass
    return frame


def test_websocket_hello_ping_pong(running_container: None) -> None:
    ws_url = BASE_URL.replace("http", "ws", 1) + "/ws"
    with connect(ws_url, open_timeout=5) as ws:
        assert json.loads(ws.recv(timeout=5))["type"] == "hello"
        ws.send(json.dumps({"v": 0, "type": "ping", "id": "smoke"}))
        assert _recv_answer(ws) == {
            "v": 0,
            "type": "pong",
            "id": "smoke",
            "payload": {},
        }


def test_version_endpoint_and_labels_match_build(
    running_container: None, provenance: dict[str, str]
) -> None:
    canonical, revision = provenance["CANONICAL"], provenance["REVISION"]
    response = httpx.get(f"{BASE_URL}/version", timeout=5)
    assert response.status_code == 200
    assert response.json() == {
        "version": canonical,
        "revision": revision,
        "dirty": canonical.endswith(".dirty"),
        "build_time": BUILD_TIME,
    }

    ws_url = BASE_URL.replace("http", "ws", 1) + "/ws"
    with connect(ws_url, open_timeout=5) as ws:
        assert json.loads(ws.recv(timeout=5))["payload"]["agent"] == canonical

    labels = json.loads(
        _run("docker", "image", "inspect", IMAGE, "--format", "{{json .Config.Labels}}")
    )
    assert labels["org.opencontainers.image.version"] == canonical
    assert labels["org.opencontainers.image.revision"] == revision
    assert labels["org.opencontainers.image.created"] == BUILD_TIME
