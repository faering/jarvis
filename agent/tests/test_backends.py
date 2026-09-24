"""Mock backends, env config and the factory."""

import io
import wave

import pytest
from pydantic import ValidationError

from jarvis_agent.backends import (
    BackendSettings,
    ChatMessage,
    HeavyRoleSettings,
    RoleSettings,
    build_backends,
)
from jarvis_agent.backends.factory import _http_client
from jarvis_agent.backends.mock import MockLLM, MockSTT, MockTTS, MockVision
from jarvis_agent.backends.openai_compat import OpenAILLM, OpenAISTT, OpenAITTS


@pytest.mark.anyio
async def test_mock_backends_are_deterministic() -> None:
    backends = build_backends(BackendSettings())
    messages: list[ChatMessage] = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello jarvis"},
    ]

    assert await backends.llm.chat(messages) == "mock reply to: hello jarvis"
    chunks = [chunk async for chunk in backends.llm.stream(messages)]
    assert "".join(chunks) == "mock reply to: hello jarvis"
    assert await backends.stt.transcribe(b"") == "mock transcript"
    assert (await backends.vision.detect(b""))[0].label == "person"

    with wave.open(io.BytesIO(await backends.tts.synthesize("hi"))) as wav:
        assert (wav.getnchannels(), wav.getframerate()) == (1, 16_000)
    await backends.aclose()


def test_env_defaults_to_mock() -> None:
    settings = BackendSettings.from_env({})
    assert settings == BackendSettings()
    assert {settings.llm.backend, settings.stt.backend, settings.tts.backend} == {"mock"}


def test_env_empty_values_count_as_unset() -> None:
    settings = BackendSettings.from_env({"JARVIS_LLM_BACKEND": "", "JARVIS_LLM_MODEL": " "})
    assert settings.llm == RoleSettings()


def test_env_reads_each_role() -> None:
    settings = BackendSettings.from_env(
        {
            "JARVIS_LLM_BACKEND": "OpenAI",
            "JARVIS_LLM_BASE_URL": "http://ollama:11434/v1",
            "JARVIS_LLM_MODEL": "qwen2.5:1.5b",
            "JARVIS_LLM_API_KEY": "secret",
            "JARVIS_TTS_BACKEND": "openai",
            "JARVIS_TTS_BASE_URL": "http://speaches:8000/v1",
            "JARVIS_TTS_MODEL": "piper",
            "JARVIS_TTS_VOICE": "amy",
        }
    )
    assert settings.llm.backend == "openai"
    assert settings.llm.model == "qwen2.5:1.5b"
    assert settings.llm.api_key is not None
    assert settings.llm.api_key.get_secret_value() == "secret"
    assert "secret" not in repr(settings)
    assert settings.stt.backend == "mock"
    assert settings.tts.voice == "amy"


@pytest.mark.parametrize(
    "env",
    [
        {"JARVIS_STT_BACKEND": "openai"},
        {"JARVIS_STT_BACKEND": "openai", "JARVIS_STT_BASE_URL": "http://x/v1"},
        {"JARVIS_STT_BACKEND": "hailo"},
    ],
)
def test_env_rejects_incomplete_or_unknown_backend(env: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        BackendSettings.from_env(env)


@pytest.mark.anyio
async def test_factory_builds_openai_backends() -> None:
    role = RoleSettings(backend="openai", base_url="http://server/v1", model="m", api_key="k")
    backends = build_backends(BackendSettings(llm=role, stt=role, tts=role))

    assert isinstance(backends.llm, OpenAILLM)
    assert isinstance(backends.stt, OpenAISTT)
    assert isinstance(backends.tts, OpenAITTS)
    assert isinstance(backends.vision, MockVision)
    await backends.aclose()


def test_factory_mixes_backends_per_role() -> None:
    llm = RoleSettings(backend="openai", base_url="http://server/v1", model="m")
    backends = build_backends(BackendSettings(llm=llm))

    assert isinstance(backends.llm, OpenAILLM)
    assert isinstance(backends.stt, MockSTT)
    assert isinstance(backends.tts, MockTTS)


def test_factory_reads_env_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_LLM_BACKEND", "openai")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "http://server/v1")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "m")

    assert isinstance(build_backends().llm, OpenAILLM)


def test_api_key_becomes_bearer_header() -> None:
    role = RoleSettings(backend="openai", base_url="http://server/v1", model="m", api_key="k")
    assert _http_client(role).headers["Authorization"] == "Bearer k"
    assert "Authorization" not in _http_client(RoleSettings()).headers


def test_heavy_llm_defaults_to_none() -> None:
    settings = BackendSettings.from_env({})
    assert settings.heavy_llm == HeavyRoleSettings()
    assert settings.heavy_llm.backend == "none"
    assert build_backends(settings).heavy_llm is None


def test_env_reads_heavy_llm() -> None:
    settings = BackendSettings.from_env(
        {
            "JARVIS_HEAVY_LLM_BACKEND": "OpenAI",
            "JARVIS_HEAVY_LLM_BASE_URL": "http://vllm:8000/v1",
            "JARVIS_HEAVY_LLM_MODEL": "qwen2.5:32b",
            "JARVIS_HEAVY_LLM_API_KEY": "secret",
        }
    )
    assert settings.heavy_llm.backend == "openai"
    assert settings.heavy_llm.base_url == "http://vllm:8000/v1"
    assert settings.heavy_llm.model == "qwen2.5:32b"
    assert "secret" not in repr(settings)
    assert settings.llm == RoleSettings()  # the local LLM is untouched


@pytest.mark.parametrize(
    "env",
    [
        {"JARVIS_HEAVY_LLM_BACKEND": "openai"},
        {"JARVIS_HEAVY_LLM_BACKEND": "vllm"},
        {"JARVIS_LLM_BACKEND": "none"},  # only the heavy role may be absent
    ],
)
def test_env_rejects_bad_heavy_llm(env: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        BackendSettings.from_env(env)


@pytest.mark.anyio
async def test_factory_builds_heavy_llm() -> None:
    openai = HeavyRoleSettings(backend="openai", base_url="http://vllm/v1", model="m", api_key="k")
    backends = build_backends(BackendSettings(heavy_llm=openai))
    assert isinstance(backends.heavy_llm, OpenAILLM)
    assert isinstance(backends.llm, MockLLM)
    await backends.aclose()

    mock = build_backends(BackendSettings(heavy_llm=HeavyRoleSettings(backend="mock")))
    assert isinstance(mock.heavy_llm, MockLLM)
