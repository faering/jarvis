"""Backend selection from environment variables (minimal; the full schema is #73).

Per role (``LLM``, ``STT``, ``TTS``)::

    JARVIS_<ROLE>_BACKEND   openai | mock   (default: mock)
    JARVIS_<ROLE>_BASE_URL  e.g. http://ollama:11434/v1   (required for openai)
    JARVIS_<ROLE>_MODEL     e.g. qwen2.5:1.5b             (required for openai)
    JARVIS_<ROLE>_API_KEY   optional bearer token
    JARVIS_TTS_VOICE        optional TTS voice

Empty values count as unset, so a copied ``.env.example`` keeps the mock defaults.
"""

import os
from collections.abc import Mapping
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

BackendKind = Literal["openai", "mock"]
ROLES = ("llm", "stt", "tts")


class RoleSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: BackendKind = "mock"
    base_url: str | None = None
    model: str | None = None
    api_key: SecretStr | None = None
    voice: str | None = None  # TTS only

    @model_validator(mode="after")
    def _openai_needs_endpoint(self) -> Self:
        if self.backend == "openai" and not (self.base_url and self.model):
            raise ValueError("the openai backend needs both base_url and model")
        return self


class BackendSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    llm: RoleSettings = RoleSettings()
    stt: RoleSettings = RoleSettings()
    tts: RoleSettings = RoleSettings()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        return cls(**{role: _role_from_env(env, role) for role in ROLES})


def _role_from_env(env: Mapping[str, str], role: str) -> RoleSettings:
    fields = ["backend", "base_url", "model", "api_key"] + (["voice"] if role == "tts" else [])
    values = {name: env.get(f"JARVIS_{role.upper()}_{name.upper()}", "").strip() for name in fields}
    if values["backend"]:
        values["backend"] = values["backend"].lower()
    return RoleSettings(**{name: value for name, value in values.items() if value})
