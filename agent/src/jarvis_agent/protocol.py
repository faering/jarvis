"""Agent <-> app WebSocket contract, envelope v0.

Every frame is a JSON object ``{"v": 0, "type": str, "id": str | null, "payload": {}}``.
This module is the Python side of the contract; it becomes the source for the shared,
versioned protocol schema (packages/protocol, #32). Bump ``PROTOCOL_VERSION`` on any
breaking change.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 0


class Envelope(BaseModel):
    """One WebSocket frame, in either direction."""

    model_config = ConfigDict(extra="forbid")

    v: Literal[0] = PROTOCOL_VERSION
    type: str = Field(min_length=1)
    id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def hello(agent_version: str) -> Envelope:
    """Server greeting sent on connect: lets the client check compatibility."""
    return Envelope(
        type="hello",
        payload={"protocol": PROTOCOL_VERSION, "agent": agent_version},
    )


def pong(request: Envelope) -> Envelope:
    return Envelope(type="pong", id=request.id)


def error(code: str, message: str, request_id: str | None = None) -> Envelope:
    return Envelope(type="error", id=request_id, payload={"code": code, "message": message})
