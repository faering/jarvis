"""Role interfaces: what the agent needs from a model, independent of who serves it.

Each role is a ``typing.Protocol``, so any object with matching async methods is a backend
(OpenAI-compatible HTTP, mock, and later on-device ones). All calls are async and must not
block the hot path.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    """One chat turn, in the OpenAI chat-completions shape."""

    role: Literal["system", "user", "assistant"]
    content: str


class BackendError(Exception):
    """A backend call failed: unreachable server, HTTP error, or malformed response."""

    def __init__(self, role: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{role} backend: {message}")
        self.role = role
        self.status_code = status_code


class LLM(Protocol):
    async def chat(self, messages: list[ChatMessage]) -> str:
        """Return the full assistant reply."""
        ...

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Yield the assistant reply as text chunks, as they are generated."""
        ...


class STT(Protocol):
    async def transcribe(self, audio: bytes, *, audio_format: str = "wav") -> str:
        """Return the text spoken in ``audio`` (encoded as ``audio_format``, e.g. wav)."""
        ...


class TTS(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Return ``text`` spoken, as WAV audio."""
        ...


@dataclass(frozen=True)
class Detection:
    """One object seen in a frame; ``box`` is (x, y, w, h), normalised to 0..1."""

    label: str
    score: float
    box: tuple[float, float, float, float]


class Vision(Protocol):
    """Stub interface: the real path (IMX500 / Hailo) is Pi-only (#35, #60)."""

    async def detect(self, frame: bytes) -> list[Detection]:
        """Return the objects detected in one camera frame."""
        ...
