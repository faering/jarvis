"""Container integration smoke test (marker: ``container``).

Unlike test_smoke.py, which drives the in-process ASGI app, this builds and runs the real
image from docker-compose.yml and talks to it over the network. It catches a broken CMD,
a HEALTHCHECK that never turns healthy, or a port/jarvis-net misconfiguration.

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
from websockets.sync.client import connect


def _compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0


pytestmark = [
    pytest.mark.container,
    pytest.mark.skipif(not _compose_available(), reason="docker compose not available"),
]

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"
NETWORK = "jarvis-net"
PROJECT = "jarvis-agent-smoke"
BASE_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8000").rstrip("/")
WAIT_TIMEOUT_S = "60"


def _run(*args: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"$ {' '.join(args)}\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="module")
def running_container() -> Iterator[None]:
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


def test_health_endpoint(running_container: None) -> None:
    response = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_hello_ping_pong(running_container: None) -> None:
    ws_url = BASE_URL.replace("http", "ws", 1) + "/ws"
    with connect(ws_url, open_timeout=5) as ws:
        assert json.loads(ws.recv(timeout=5))["type"] == "hello"
        ws.send(json.dumps({"v": 0, "type": "ping", "id": "smoke"}))
        assert json.loads(ws.recv(timeout=5)) == {
            "v": 0,
            "type": "pong",
            "id": "smoke",
            "payload": {},
        }
