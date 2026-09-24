"""Speech output: a non-blocking producer/consumer queue from reply text to audio.

Producers (the voice loop) hand text to ``SpeechQueue`` without ever awaiting TTS; a
background pipeline segments it into sentences/clauses, synthesizes and plays them, and a
barge-in (``interrupt()``) cuts it off at once. Audio output sits behind ``AudioSink``.
"""

from jarvis_agent.speech.queue import SpeechEvent, SpeechEventKind, SpeechQueue
from jarvis_agent.speech.segmenter import Segmenter
from jarvis_agent.speech.sink import AudioSink, NullSink

__all__ = [
    "AudioSink",
    "NullSink",
    "Segmenter",
    "SpeechEvent",
    "SpeechEventKind",
    "SpeechQueue",
]
