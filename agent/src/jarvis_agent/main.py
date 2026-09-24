"""ASGI entrypoint: health, version and the WebSocket the Tauri app connects to."""

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from jarvis_agent import protocol
from jarvis_agent.version import BuildInfo, build_info

app = FastAPI(title="Jarvis agent", version=build_info()["version"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> BuildInfo:
    """Build provenance; ``version`` is the same canonical string the app displays."""
    return build_info()


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await _send(websocket, protocol.hello(build_info()["version"]))
    while True:
        # receive() rather than receive_text(): a binary frame must yield an error reply,
        # not a KeyError that kills the connection.
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        text = message.get("text")
        if text is None:
            reply = protocol.error("bad_frame", "binary frames are not supported")
        else:
            reply = _handle(text)
        try:
            await _send(websocket, reply)
        except WebSocketDisconnect:
            return


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
