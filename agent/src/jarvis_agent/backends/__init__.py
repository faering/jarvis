"""Role backends: LLM, STT, TTS and Vision interfaces with pluggable implementations.

Pick implementations with ``build_backends()`` (configured from ``JARVIS_*`` env vars; see
``config``). Mocks are the default, so the agent runs with no model servers at all.
"""

from jarvis_agent.backends.base import (
    LLM,
    STT,
    TTS,
    BackendError,
    ChatMessage,
    Detection,
    Vision,
)
from jarvis_agent.backends.config import BackendSettings, RoleSettings
from jarvis_agent.backends.factory import Backends, build_backends

__all__ = [
    "LLM",
    "STT",
    "TTS",
    "BackendError",
    "BackendSettings",
    "Backends",
    "ChatMessage",
    "Detection",
    "RoleSettings",
    "Vision",
    "build_backends",
]
