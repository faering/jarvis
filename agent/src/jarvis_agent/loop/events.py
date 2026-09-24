"""What the voice loop reports to the UI: state changes, transcripts and reply text."""

from dataclasses import dataclass
from enum import StrEnum


class LoopState(StrEnum):
    """The states of docs/state-machine.md."""

    IDLE = "idle"
    LISTENING = "listening"
    ROUTING = "routing"
    SPEAKING = "speaking"
    OFFLOADED = "offloaded"


@dataclass(frozen=True)
class StateChanged:
    state: LoopState


@dataclass(frozen=True)
class Transcript:
    """What the user said (the STT result, or the text as typed)."""

    text: str


@dataclass(frozen=True)
class ReplyText:
    """Reply text for the UI. Streaming frames carry ``delta`` with ``done=False``; the last
    frame of a reply carries the full ``text`` with ``done=True``. An offloaded reply is a
    single ``done`` frame. ``degraded``: the heavy model was wanted but could not answer."""

    delta: str | None = None
    text: str | None = None
    done: bool = False
    degraded: bool = False


type LoopEvent = StateChanged | Transcript | ReplyText
