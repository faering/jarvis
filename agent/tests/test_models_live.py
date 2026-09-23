"""Live role-backend test against the local model stack (marker: ``models``).

Calls each real OpenAI-compatible backend once. Needs the model services running
(``docker compose up -d``, first run downloads the models); too heavy for CI. Opt-in:
    uv run --frozen --extra test pytest -m models

Endpoints default to the compose service names on jarvis-net (reachable from the
devcontainer); override with the usual ``JARVIS_<ROLE>_*`` env vars.
"""

import os
import re
from collections.abc import AsyncIterator

import pytest

from jarvis_agent.backends import Backends, BackendSettings, ChatMessage, build_backends

pytestmark = [pytest.mark.models, pytest.mark.anyio]

COMPOSE_DEFAULTS = {
    "JARVIS_LLM_BACKEND": "openai",
    "JARVIS_LLM_BASE_URL": "http://ollama:11434/v1",
    "JARVIS_LLM_MODEL": "qwen2.5:1.5b",
    "JARVIS_STT_BACKEND": "openai",
    "JARVIS_STT_BASE_URL": "http://speaches:8000/v1",
    "JARVIS_STT_MODEL": "Systran/faster-whisper-base.en",
    "JARVIS_TTS_BACKEND": "openai",
    "JARVIS_TTS_BASE_URL": "http://speaches:8000/v1",
    "JARVIS_TTS_MODEL": "speaches-ai/piper-en_US-lessac-medium",
    "JARVIS_TTS_VOICE": "lessac",
}


@pytest.fixture
async def backends() -> AsyncIterator[Backends]:
    overrides = {key: value for key, value in os.environ.items() if key.startswith("JARVIS_")}
    built = build_backends(BackendSettings.from_env({**COMPOSE_DEFAULTS, **overrides}))
    yield built
    await built.aclose()


async def test_llm_chat_and_stream(backends: Backends) -> None:
    messages: list[ChatMessage] = [
        {"role": "user", "content": "Reply with one short sentence: say hello."}
    ]

    reply = await backends.llm.chat(messages)
    chunks = [chunk async for chunk in backends.llm.stream(messages)]

    assert reply.strip()
    # A short reply may legitimately arrive as a single delta; only require content.
    assert chunks
    assert "".join(chunks).strip()


async def test_tts_to_stt_round_trip(backends: Backends) -> None:
    audio = await backends.tts.synthesize("The quick brown fox jumps over the lazy dog.")
    assert audio.startswith(b"RIFF")  # WAV

    text = await backends.stt.transcribe(audio)

    words = set(re.findall(r"[a-z]+", text.lower()))
    assert {"quick", "brown", "fox"} <= words, text
