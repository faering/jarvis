"""The model catalogue and how a device's role assignment becomes backend settings.

``catalogue.toml`` lists every model Jarvis knows; a device assigns one per role in its
config (``[models]``) and says where each runtime lives (``[runtimes.<name>]``).
``resolve_backends()`` turns that into the ``BackendSettings`` that ``build_backends()``
uses. Explicit ``backends.<role>.*`` values (e.g. ``JARVIS_LLM_MODEL``) still win, field by
field, so a quick experiment needs no catalogue edit.
"""

import tomllib
from collections.abc import Mapping
from functools import cache
from importlib import resources
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from jarvis_agent.backends.config import BackendSettings

Role = Literal["llm", "heavy_llm", "stt", "tts", "vlm", "wake_word", "embed", "vision"]
ROLES: tuple[Role, ...] = ("llm", "heavy_llm", "stt", "tts", "vlm", "wake_word", "embed", "vision")
# Roles with a backend today; the others can be assigned and listed ahead of their wiring.
WIRED: tuple[Role, ...] = ("llm", "heavy_llm", "stt", "tts")
# Runtimes that aren't OpenAI-compatible HTTP servers: no backend for them yet (#60, #61).
NOT_WIRED_RUNTIMES = frozenset({"hailo", "imx500"})


class ModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: tuple[Role, ...] = Field(min_length=1)
    runtime: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: str = Field(min_length=1)
    voice: str | None = None
    size: str | None = None
    licence: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _voice_is_for_tts(self) -> Self:
        if self.voice is not None and "tts" not in self.roles:
            raise ValueError("voice is only for tts models")
        return self


class Catalogue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: dict[str, ModelEntry] = {}

    def for_role(self, role: Role) -> list[str]:
        return sorted(mid for mid, entry in self.model.items() if role in entry.roles)


class RuntimeConfig(BaseModel):
    """Where a runtime is reached on this device."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str | None = None
    api_key: SecretStr | None = None


@cache
def load_catalogue() -> Catalogue:
    """The catalogue shipped with the agent (read once)."""
    text = (resources.files("jarvis_agent.models") / "catalogue.toml").read_text()
    return Catalogue.model_validate(tomllib.loads(text))


class ModelProblems(ValueError):
    """The role assignment doesn't fit the catalogue; ``problems`` maps role -> message."""

    def __init__(self, problems: dict[str, str]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"models.{r}: {m}" for r, m in problems.items()))


def resolve_backends(
    models: Mapping[str, str],
    runtimes: Mapping[str, RuntimeConfig],
    backends: BackendSettings,
    catalogue: Catalogue,
) -> BackendSettings:
    """``backends`` with each assigned wired role filled in from the catalogue.

    Per role, fields set explicitly in ``backends`` win; an explicit non-``openai`` backend
    (``mock``, ``none``) keeps the role as it is. Raises ``ModelProblems`` listing every
    role whose assignment is unknown, the wrong role, or has no runtime address.
    """
    problems: dict[str, str] = {}
    updates = {}
    for role, model_id in models.items():
        entry = catalogue.model.get(model_id)
        if entry is None:
            known = ", ".join(catalogue.for_role(role)) or "none yet"  # type: ignore[arg-type]
            problems[role] = f"unknown model {model_id!r} (catalogue models for {role}: {known})"
            continue
        if role not in entry.roles:
            roles = ", ".join(entry.roles)
            problems[role] = f"{model_id!r} is not a {role} model (its roles: {roles})"
            continue
        if role not in WIRED:
            continue
        current = getattr(backends, role)
        explicit = current.model_fields_set
        if "backend" in explicit and current.backend != "openai":
            continue  # e.g. JARVIS_LLM_BACKEND=mock: the explicit choice wins
        if entry.runtime in NOT_WIRED_RUNTIMES:
            problems[role] = f"{model_id!r} runs on {entry.runtime}, which isn't wired yet"
            continue
        runtime = runtimes.get(entry.runtime, RuntimeConfig())
        base_url = current.base_url if "base_url" in explicit else runtime.base_url
        if not base_url:
            env = f"JARVIS_RUNTIME_{entry.runtime.upper()}_URL"
            problems[role] = (
                f"{model_id!r} runs on {entry.runtime!r}, which has no address here "
                f"(set [runtimes.{entry.runtime}] base_url or {env})"
            )
            continue
        fields = {
            "backend": "openai",
            "base_url": base_url,
            "model": current.model if "model" in explicit else entry.source,
            "api_key": current.api_key if "api_key" in explicit else runtime.api_key,
        }
        if role == "tts":
            fields["voice"] = current.voice if "voice" in explicit else entry.voice
        updates[role] = type(current).model_validate(fields)
    if problems:
        raise ModelProblems(problems)
    return backends.model_copy(update=updates)
