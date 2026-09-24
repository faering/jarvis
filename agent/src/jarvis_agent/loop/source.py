"""The input seam: where utterances come from.

On the Pi an ``AudioSource`` wraps the mic, wake word and VAD (hardware, not here): it
reports ``Wake`` when listening starts, ``Utterance`` at the turn boundary and ``Cancel`` on
a listening timeout. Text input (the app over WebSocket) skips the source and calls
``VoiceLoop.say`` directly.
"""

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Wake:
    """Wake word or touch: start listening (a barge-in if Jarvis is speaking)."""


@dataclass(frozen=True)
class Cancel:
    """Listening timed out or was cancelled: back to Idle."""


@dataclass(frozen=True)
class Utterance:
    """One user turn, ended by a turn boundary: recorded ``audio`` (transcribed by STT) or
    ``text``. ``deep`` asks for the heavy route (planning, long-form answers)."""

    text: str | None = None
    audio: bytes | None = None
    audio_format: str = "wav"
    deep: bool = False

    def __post_init__(self) -> None:
        if (self.text is None) == (self.audio is None):
            raise ValueError("an utterance has exactly one of text or audio")


type SourceEvent = Wake | Cancel | Utterance


class AudioSource(Protocol):
    def events(self) -> AsyncIterator[SourceEvent]:
        """Yield input events as they happen; ends when the source closes."""
        ...


class ScriptedSource:
    """Replays a fixed list of events: for tests and the devcontainer (no mic)."""

    def __init__(self, events: Iterable[SourceEvent]) -> None:
        self._events = list(events)

    async def events(self) -> AsyncIterator[SourceEvent]:
        for event in self._events:
            yield event
