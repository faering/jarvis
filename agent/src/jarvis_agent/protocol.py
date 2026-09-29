"""Agent <-> app WebSocket contract, envelope v0.

Every frame is a JSON object ``{"v": 0, "type": str, "id": str | null, "payload": {}}``.
``v`` is required: it is the compatibility discriminator. This module is the Python side
of the contract; it becomes the source for the shared, versioned protocol schema
(packages/protocol, #32). Bump ``PROTOCOL_VERSION`` on any breaking change.

Message types (payloads):

- agent -> client: ``hello`` {protocol, agent}, ``pong``, ``error`` {code, message};
  voice loop events: ``state`` {state}, ``transcript`` {text},
  ``reply`` {delta, done: false, degraded} while streaming, then
  ``reply`` {text, done: true, degraded, spoken?}: the reply is complete (memory is
  best-effort). ``spoken: false`` only when speech was refused, dropped or had already
  failed when the reply completed; absent means it was accepted for speech (playback runs
  on after ``done``, so a later failure is only logged).
  ``command`` {name}: ask the app to run a command from the schema's closed list
  (ADR 0013); for now only after a fixed phrase (``jarvis_agent.commands``, #223).
- client -> agent: ``ping``; ``say`` {text, deep?} (a text utterance for the voice loop).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = 0


class Envelope(BaseModel):
    """One WebSocket frame, in either direction."""

    model_config = ConfigDict(extra="forbid")

    v: int = Field(strict=True)
    type: str = Field(min_length=1)
    id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("v")
    @classmethod
    def _supported_version(cls, v: int) -> int:
        if v != PROTOCOL_VERSION:
            raise ValueError(f"unsupported protocol version {v}; expected {PROTOCOL_VERSION}")
        return v


class SayPayload(BaseModel):
    """``say``: a typed utterance. ``deep`` asks for the heavy route."""

    # Unknown fields are ignored: a newer app may add optional say fields (additive).
    model_config = ConfigDict(extra="ignore")

    text: str = Field(strict=True, min_length=1)
    deep: bool = Field(default=False, strict=True)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("text is blank")
        return text


def hello(agent_version: str) -> Envelope:
    """Server greeting sent on connect: lets the client check compatibility."""
    return Envelope(
        v=PROTOCOL_VERSION,
        type="hello",
        payload={"protocol": PROTOCOL_VERSION, "agent": agent_version},
    )


def pong(request: Envelope) -> Envelope:
    return Envelope(v=PROTOCOL_VERSION, type="pong", id=request.id)


def _traced(payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
    """Add the turn's ``trace_id`` (docs/logging.md) when there is one."""
    if trace_id is not None:
        payload["trace_id"] = trace_id
    return payload


def error(
    code: str, message: str, request_id: str | None = None, *, trace_id: str | None = None
) -> Envelope:
    return Envelope(
        v=PROTOCOL_VERSION,
        type="error",
        id=request_id,
        payload=_traced({"code": code, "message": message}, trace_id),
    )


def state(value: str, *, trace_id: str | None = None) -> Envelope:
    """The voice loop's state: idle | listening | routing | speaking | offloaded."""
    return Envelope(v=PROTOCOL_VERSION, type="state", payload=_traced({"state": value}, trace_id))


def transcript(text: str, *, trace_id: str | None = None) -> Envelope:
    return Envelope(
        v=PROTOCOL_VERSION, type="transcript", payload=_traced({"text": text}, trace_id)
    )


def reply(
    *,
    delta: str | None = None,
    text: str | None = None,
    done: bool,
    degraded: bool,
    spoken: bool = True,
    trace_id: str | None = None,
) -> Envelope:
    """Reply text: ``delta`` frames while streaming, then one ``done`` frame with ``text``.
    ``spoken: false`` is added only when the reply was not (fully) accepted for speech, or
    its speech had already failed (see ``ReplyText``)."""
    payload: dict[str, Any] = {"done": done, "degraded": degraded}
    if not spoken:
        payload["spoken"] = False
    if delta is not None:
        payload["delta"] = delta
    if text is not None:
        payload["text"] = text
    return Envelope(v=PROTOCOL_VERSION, type="reply", payload=_traced(payload, trace_id))


def command(name: str, *, trace_id: str | None = None) -> Envelope:
    """Ask the app to run ``name`` (the schema's ``$defs.command`` list; ADR 0013)."""
    return Envelope(v=PROTOCOL_VERSION, type="command", payload=_traced({"name": name}, trace_id))
