"""Runtime wiring: FastAPI lifespan startup/shutdown and the voice loop over WebSocket."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from jarvis_agent.loop import LoopState, ReplyText
from jarvis_agent.main import _event, app
from jarvis_agent.runtime import Runtime
from jarvis_agent.store import StoreError


@pytest.fixture
def agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock backends and an in-memory store: no model servers, no /data."""
    monkeypatch.setenv("JARVIS_STATE_DB", ":memory:")
    for role in ("LLM", "STT", "TTS", "HEAVY_LLM"):
        monkeypatch.setenv(f"JARVIS_{role}_BACKEND", "mock")


@pytest.fixture
def client(agent_env: None) -> Iterator[TestClient]:
    """The app with its lifespan running."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def ws(client: TestClient) -> Iterator[WebSocketTestSession]:
    with client.websocket_connect("/ws") as session:
        assert session.receive_json()["type"] == "hello"
        # Then the loop's current state, so a new client doesn't wait for the next change.
        assert session.receive_json() == {
            "v": 0,
            "type": "state",
            "id": None,
            "payload": {"state": "idle"},
        }
        yield session


def _frames_until_idle(ws: WebSocketTestSession) -> list[dict[str, Any]]:
    frames = []
    while True:
        frames.append(ws.receive_json())
        if frames[-1] == {"v": 0, "type": "state", "id": None, "payload": {"state": "idle"}}:
            if any(f["type"] == "reply" and f["payload"]["done"] for f in frames):
                return frames


def test_lifespan_starts_and_stops_the_runtime(agent_env: None) -> None:
    with TestClient(app) as client:
        runtime: Runtime = app.state.runtime
        assert runtime.loop.state is LoopState.IDLE
        assert client.get("/health").json() == {"status": "ok"}

    assert not hasattr(app.state, "runtime")
    with pytest.raises(StoreError):
        asyncio.run(runtime.state.memory.recent())


def test_say_streams_transcript_reply_and_state(ws: WebSocketTestSession) -> None:
    ws.send_json({"v": 0, "type": "say", "id": "1", "payload": {"text": "hello"}})
    frames = [(f["type"], f["payload"]) for f in _frames_until_idle(ws)]

    assert frames == [
        ("state", {"state": "listening"}),
        ("state", {"state": "routing"}),
        ("transcript", {"text": "hello"}),
        ("state", {"state": "speaking"}),
        ("reply", {"delta": "mock ", "done": False, "degraded": False}),
        ("reply", {"delta": "reply ", "done": False, "degraded": False}),
        ("reply", {"delta": "to: ", "done": False, "degraded": False}),
        ("reply", {"delta": "hello", "done": False, "degraded": False}),
        ("reply", {"text": "mock reply to: hello", "done": True, "degraded": False}),
        ("state", {"state": "idle"}),
    ]


def test_deep_say_is_offloaded(ws: WebSocketTestSession) -> None:
    ws.send_json({"v": 0, "type": "say", "payload": {"text": "plan my week", "deep": True}})
    frames = _frames_until_idle(ws)

    states = [f["payload"]["state"] for f in frames if f["type"] == "state"]
    assert states[:4] == ["listening", "routing", "offloaded", "idle"]
    replies = [f["payload"] for f in frames if f["type"] == "reply"]
    heavy = "mock heavy reply to: plan my week"
    assert replies == [{"text": heavy, "done": True, "degraded": False}]


@pytest.mark.parametrize(
    "payload", [{}, {"text": ""}, {"text": "   "}, {"text": 1}, {"text": "hi", "x": 1}]
)
def test_bad_say_gets_error_and_keeps_connection(
    ws: WebSocketTestSession, payload: dict[str, Any]
) -> None:
    ws.send_json({"v": 0, "type": "say", "id": "7", "payload": payload})
    reply = ws.receive_json()
    assert (reply["type"], reply["id"], reply["payload"]["code"]) == ("error", "7", "bad_payload")

    ws.send_json({"v": 0, "type": "ping", "id": "after"})
    assert ws.receive_json()["type"] == "pong"


def test_say_without_runtime_is_unavailable() -> None:
    with TestClient(app).websocket_connect("/ws") as ws:  # no lifespan: no voice loop
        ws.receive_json()  # hello
        ws.send_json({"v": 0, "type": "say", "id": "1", "payload": {"text": "hi"}})
        assert ws.receive_json()["payload"]["code"] == "unavailable"


def test_reply_not_spoken_is_flagged_additively() -> None:
    spoken = _event(ReplyText(text="hi", done=True)).payload
    unspoken = _event(ReplyText(text="hi", done=True, spoken=False)).payload
    assert spoken == {"text": "hi", "done": True, "degraded": False}  # unchanged
    assert unspoken == {"text": "hi", "done": True, "degraded": False, "spoken": False}
