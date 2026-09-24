from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from jarvis_agent.main import app
from jarvis_agent.protocol import PROTOCOL_VERSION
from jarvis_agent.version import build_info


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def ws(client: TestClient) -> Iterator[WebSocketTestSession]:
    with client.websocket_connect("/ws") as session:
        session.receive_json()  # hello
        yield session


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_hello_on_connect(client: TestClient) -> None:
    with client.websocket_connect("/ws") as session:
        assert session.receive_json() == {
            "v": 0,
            "type": "hello",
            "id": None,
            "payload": {"protocol": PROTOCOL_VERSION, "agent": build_info()["version"]},
        }


def test_ping_pong(ws: WebSocketTestSession) -> None:
    ws.send_json({"v": 0, "type": "ping", "id": "1"})
    assert ws.receive_json() == {"v": 0, "type": "pong", "id": "1", "payload": {}}


@pytest.mark.parametrize(
    ("frame", "code"),
    [
        ("not json", "bad_json"),
        ('{"v": 1, "type": "ping"}', "bad_envelope"),
        ('{"v": 0}', "bad_envelope"),
        ('{"type": "ping"}', "bad_envelope"),  # v is required
        ('{"v": "0", "type": "ping"}', "bad_envelope"),
        ('{"v": 0, "type": "ping", "extra": true}', "bad_envelope"),
        ('{"v": 0, "type": "nope", "id": "7"}', "unknown_type"),
    ],
)
def test_bad_frames_get_error_and_keep_connection(
    ws: WebSocketTestSession, frame: str, code: str
) -> None:
    ws.send_text(frame)
    reply = ws.receive_json()
    assert reply["type"] == "error"
    assert reply["payload"]["code"] == code

    ws.send_json({"v": 0, "type": "ping", "id": "after"})
    assert ws.receive_json()["type"] == "pong"


def test_binary_frame_gets_error_and_keeps_connection(ws: WebSocketTestSession) -> None:
    ws.send_bytes(b"\x00\x01")
    reply = ws.receive_json()
    assert reply["type"] == "error"
    assert reply["payload"]["code"] == "bad_frame"

    ws.send_json({"v": 0, "type": "ping", "id": "after"})
    assert ws.receive_json()["type"] == "pong"
