"""ASGI entrypoint: health check and the WebSocket the Tauri app connects to."""

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from jarvis_agent import __version__, protocol

app = FastAPI(title="Jarvis agent", version=__version__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await _send(websocket, protocol.hello(__version__))
    try:
        while True:
            reply = _handle(await websocket.receive_text())
            await _send(websocket, reply)
    except WebSocketDisconnect:
        pass


def _handle(raw: str) -> protocol.Envelope:
    """Map one inbound frame to its reply. Bad input yields an error, never a disconnect."""
    try:
        request = protocol.Envelope.model_validate(json.loads(raw))
    except json.JSONDecodeError:
        return protocol.error("bad_json", "frame is not valid JSON")
    except ValidationError as exc:
        return protocol.error("bad_envelope", str(exc.errors(include_url=False)))

    match request.type:
        case "ping":
            return protocol.pong(request)
        case _:
            return protocol.error("unknown_type", f"unknown type {request.type!r}", request.id)


async def _send(websocket: WebSocket, envelope: protocol.Envelope) -> None:
    await websocket.send_text(envelope.model_dump_json())
