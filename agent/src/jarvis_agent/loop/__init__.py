"""The always-on voice loop: Idle -> Listening -> Routing -> Speaking / Offloaded.

``VoiceLoop`` drives the agent state machine (docs/state-machine.md). Input arrives as
source events (``Wake``, ``Cancel``, ``Utterance``) from an ``AudioSource`` (mic + wake word
+ VAD on the Pi) or as text (``VoiceLoop.say``, e.g. from the app over WebSocket). Replies
stream from the local LLM into the ``SpeechQueue``; heavy tasks are offloaded and spoken
when they finish. UI-facing events (``LoopEvent``) go to subscribers.
"""

from jarvis_agent.loop.events import LoopEvent, LoopState, ReplyText, StateChanged, Transcript
from jarvis_agent.loop.source import (
    AudioSource,
    Cancel,
    ScriptedSource,
    SourceEvent,
    Utterance,
    Wake,
)
from jarvis_agent.loop.voice import LoopBusy, VoiceLoop

__all__ = [
    "AudioSource",
    "Cancel",
    "LoopBusy",
    "LoopEvent",
    "LoopState",
    "ReplyText",
    "ScriptedSource",
    "SourceEvent",
    "StateChanged",
    "Transcript",
    "Utterance",
    "VoiceLoop",
    "Wake",
]
