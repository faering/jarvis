"""ASGI entrypoint: health, version and the WebSocket the Tauri app connects to."""

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from jarvis_agent import protocol
from jarvis_agent.loop import LoopEvent, ReplyText, StateChanged, Transcript, VoiceLoop
from jarvis_agent.runtime import Runtime, lifespan
from jarvis_agent.version import BuildInfo, build_info

log = logging.getLogger(__name__)

# Frames waiting to be sent to one client. A client this far behind is too slow: new
# frames are dropped (and logged) rather than stalling the voice loop.
OUTBOX_SIZE = 256

app = FastAPI(title="Jarvis agent", version=build_info()["version"], lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> BuildInfo:
    """Build provenance; ``version`` is the agent's canonical version (the app has its own)."""
    return build_info()


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await _send(websocket, protocol.hello(build_info()["version"]))
    # One writer per connection, so replies and voice loop events never interleave sends.
    outbox: asyncio.Queue[protocol.Envelope] = asyncio.Queue(maxsize=OUTBOX_SIZE)
    runtime: Runtime | None = getattr(websocket.app.state, "runtime", None)
    loop = runtime.loop if runtime is not None else None
    unsubscribe = loop.subscribe(lambda event: _post(outbox, _event(event))) if loop else None
    if loop is not None:
        # A new client learns the current state right away, not at the next change.
        _post(outbox, protocol.state(loop.state.value))
    writer = asyncio.create_task(_write(websocket, outbox), name="ws-writer")
    try:
        while True:
            # receive() rather than receive_text(): a binary frame must yield an error
            # reply, not a KeyError that kills the connection.
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                reply = protocol.error("bad_frame", "binary frames are not supported")
            else:
                reply = _handle(text, loop)
            if reply is not None:
                _post(outbox, reply)
    finally:
        if unsubscribe is not None:
            unsubscribe()
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)


def _handle(raw: str, loop: VoiceLoop | None) -> protocol.Envelope | None:
    """Map one inbound frame to its reply (None: the answer comes as loop events). Bad input
    yields an error, never a disconnect."""
    try:
        request = protocol.Envelope.model_validate(json.loads(raw))
    except json.JSONDecodeError:
        return protocol.error("bad_json", "frame is not valid JSON")
    except ValidationError as exc:
        return protocol.error("bad_envelope", str(exc.errors(include_url=False)))

    match request.type:
        case "ping":
            return protocol.pong(request)
        case "say":
            return _say(request, loop)
        case _:
            return protocol.error("unknown_type", f"unknown type {request.type!r}", request.id)


def _say(request: protocol.Envelope, loop: VoiceLoop | None) -> protocol.Envelope | None:
    try:
        say = protocol.SayPayload.model_validate(request.payload)
    except ValidationError as exc:
        return protocol.error("bad_payload", str(exc.errors(include_url=False)), request.id)
    if loop is None:
        return protocol.error("unavailable", "the voice loop is not running", request.id)
    loop.say(say.text, deep=say.deep)
    return None


def _event(event: LoopEvent) -> protocol.Envelope:
    match event:
        case StateChanged(state):
            return protocol.state(state.value)
        case Transcript(text):
            return protocol.transcript(text)
        case ReplyText(delta, text, done, degraded):
            return protocol.reply(delta=delta, text=text, done=done, degraded=degraded)


def _post(outbox: asyncio.Queue[protocol.Envelope], envelope: protocol.Envelope) -> None:
    try:
        outbox.put_nowait(envelope)
    except asyncio.QueueFull:
        log.warning("ws: client too slow, dropped a %r frame", envelope.type)


async def _write(websocket: WebSocket, outbox: asyncio.Queue[protocol.Envelope]) -> None:
    try:
        while True:
            await _send(websocket, await outbox.get())
    except WebSocketDisconnect:
        return


async def _send(websocket: WebSocket, envelope: protocol.Envelope) -> None:
    await websocket.send_text(envelope.model_dump_json())
