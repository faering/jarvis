"""Agent <-> app WebSocket contract, envelope v0.

Every frame is a JSON object ``{"v": 0, "type": str, "id": str | null, "payload": {}}``.
``v`` is required: it is the compatibility discriminator. This module is the Python side
of the contract; it becomes the source for the shared, versioned protocol schema
(packages/protocol, #32). Bump ``PROTOCOL_VERSION`` on any breaking change.
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


def hello(agent_version: str) -> Envelope:
    """Server greeting sent on connect: lets the client check compatibility."""
    return Envelope(
        v=PROTOCOL_VERSION,
        type="hello",
        payload={"protocol": PROTOCOL_VERSION, "agent": agent_version},
    )


def pong(request: Envelope) -> Envelope:
    return Envelope(v=PROTOCOL_VERSION, type="pong", id=request.id)


def error(code: str, message: str, request_id: str | None = None) -> Envelope:
    return Envelope(
        v=PROTOCOL_VERSION,
        type="error",
        id=request_id,
        payload={"code": code, "message": message},
    )
