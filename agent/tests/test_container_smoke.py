"""Container integration smoke test.

Unlike test_smoke.py (which drives the in-process ASGI app via FastAPI's TestClient and
never touches Docker), this builds and runs the *actual* image from docker-compose.yml and
talks to it over the network. It's what catches a broken CMD, a HEALTHCHECK that never
turns healthy, or a port/jarvis-net misconfiguration — none of which TestClient can see.

Requires the Docker CLI with the compose plugin; skipped when unavailable so the rest of
the suite stays runnable without Docker.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import websockets.sync.client  # transitive via uvicorn[standard]; no extra dependency needed

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
NETWORK = "jarvis-net"
PROJECT = "jarvis-agent-smoke"
BASE_URL = "http://127.0.0.1:8000"
WAIT_TIMEOUT_S = "60"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"$ {' '.join(args)}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result


@pytest.fixture(scope="module")
def running_container() -> Iterator[None]:
    # jarvis-net is normally created once by the devcontainer's initializeCommand (see
    # docker-compose.yml); create it here too so this test is self-contained in CI.
    network_exists = (
        subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True).returncode
        == 0
    )
    if not network_exists:
        _run("docker", "network", "create", NETWORK)

    compose = ["docker", "compose", "-f", str(COMPOSE_FILE), "-p", PROJECT]
    try:
        _run(*compose, "up", "--build", "--detach", "--wait", "--wait-timeout", WAIT_TIMEOUT_S)
        yield
    finally:
        subprocess.run([*compose, "down", "--volumes"], capture_output=True)
        if not network_exists:
            subprocess.run(["docker", "network", "rm", NETWORK], capture_output=True)


def test_health_endpoint(running_container: None) -> None:
    response = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_hello_ping_pong(running_container: None) -> None:
    with websockets.sync.client.connect(f"{BASE_URL.replace('http', 'ws')}/ws") as ws:
        hello = json.loads(ws.recv())
        assert hello["type"] == "hello"

        ws.send(json.dumps({"v": 0, "type": "ping", "id": "smoke"}))
        assert json.loads(ws.recv()) == {"v": 0, "type": "pong", "id": "smoke", "payload": {}}
