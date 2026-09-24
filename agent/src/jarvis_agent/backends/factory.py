"""Build the role backends from settings. Nothing connects until a backend is used."""

from dataclasses import dataclass, field

import httpx

from jarvis_agent.backends.base import LLM, STT, TTS, Vision
from jarvis_agent.backends.config import BackendSettings, RoleSettings
from jarvis_agent.backends.mock import MockLLM, MockSTT, MockTTS, MockVision
from jarvis_agent.backends.openai_compat import OpenAILLM, OpenAISTT, OpenAITTS

# Local models on a CPU can take a while to answer; connecting should not.
HTTP_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


@dataclass
class Backends:
    llm: LLM
    stt: STT
    tts: TTS
    vision: Vision
    heavy_llm: LLM | None = None  # None = not configured; heavy tasks use ``llm``
    _clients: list[httpx.AsyncClient] = field(default_factory=list, repr=False)

    async def aclose(self) -> None:
        for client in self._clients:
            await client.aclose()


def build_backends(settings: BackendSettings | None = None) -> Backends:
    settings = BackendSettings.from_env() if settings is None else settings
    clients: list[httpx.AsyncClient] = []

    def client_for(role: RoleSettings) -> httpx.AsyncClient:
        client = _http_client(role)
        clients.append(client)
        return client

    llm: LLM = MockLLM()
    if settings.llm.backend == "openai":
        llm = OpenAILLM(client_for(settings.llm), _model(settings.llm))

    stt: STT = MockSTT()
    if settings.stt.backend == "openai":
        stt = OpenAISTT(client_for(settings.stt), _model(settings.stt))

    tts: TTS = MockTTS()
    if settings.tts.backend == "openai":
        tts = OpenAITTS(client_for(settings.tts), _model(settings.tts), settings.tts.voice)

    heavy_llm: LLM | None = None
    if settings.heavy_llm.backend == "openai":
        heavy_llm = OpenAILLM(client_for(settings.heavy_llm), _model(settings.heavy_llm))
    elif settings.heavy_llm.backend == "mock":
        heavy_llm = MockLLM(name="mock heavy")

    return Backends(
        llm=llm, stt=stt, tts=tts, vision=MockVision(), heavy_llm=heavy_llm, _clients=clients
    )


def _http_client(role: RoleSettings) -> httpx.AsyncClient:
    headers = {}
    if role.api_key is not None:
        headers["Authorization"] = f"Bearer {role.api_key.get_secret_value()}"
    return httpx.AsyncClient(base_url=role.base_url or "", headers=headers, timeout=HTTP_TIMEOUT)


def _model(role: RoleSettings) -> str:
    assert role.model is not None  # guaranteed by RoleSettings validation for openai
    return role.model
