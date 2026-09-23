"""Deterministic in-process backends for tests, CI and the devcontainer (the default)."""

import io
import wave
from collections.abc import AsyncIterator

from jarvis_agent.backends.base import ChatMessage, Detection


class MockLLM:
    """Echoes the last user message."""

    async def chat(self, messages: list[ChatMessage]) -> str:
        return _mock_reply(messages)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        words = _mock_reply(messages).split(" ")
        for index, word in enumerate(words):
            yield word if index == len(words) - 1 else word + " "


class MockSTT:
    """Returns a fixed transcript, whatever the audio."""

    def __init__(self, transcript: str = "mock transcript") -> None:
        self.transcript = transcript

    async def transcribe(self, audio: bytes, *, audio_format: str = "wav") -> str:
        return self.transcript


class MockTTS:
    """Returns a short, valid, silent WAV (16 kHz mono, 16-bit)."""

    async def synthesize(self, text: str) -> bytes:
        return silent_wav(seconds=0.1)


class MockVision:
    """Always sees one person in the middle of the frame."""

    async def detect(self, frame: bytes) -> list[Detection]:
        return [Detection(label="person", score=1.0, box=(0.25, 0.25, 0.5, 0.5))]


def silent_wav(seconds: float, sample_rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(seconds * sample_rate))
    return buffer.getvalue()


def _mock_reply(messages: list[ChatMessage]) -> str:
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return f"mock reply to: {last_user}"
