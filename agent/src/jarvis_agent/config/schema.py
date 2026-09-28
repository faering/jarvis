"""The validated agent config: hardware, role backends, state store, capabilities, logging.

Backends and store reuse ``BackendSettings`` / ``StoreSettings`` as-is, so the layered
config feeds ``build_backends()`` and ``open_state()`` unchanged.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator

from jarvis_agent.backends.config import BackendSettings
from jarvis_agent.hardware import Toggle
from jarvis_agent.logs.config import LogSettings
from jarvis_agent.models import Role, RuntimeConfig, load_catalogue, resolve_backends
from jarvis_agent.store.config import StoreSettings


class HardwareConfig(BaseModel):
    """``on`` = present (no probe), ``off`` = ignore it, ``auto`` = probe at startup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hailo: Toggle = "auto"
    imx500: Toggle = "auto"
    mic: Toggle = "auto"
    speaker: Toggle = "auto"
    display: Toggle = "auto"


class CapabilityConfig(BaseModel):
    """``enabled``: ``auto`` = on if its requirements are met; ``on`` = warn loudly if not.

    ``prefer`` lists the allowed providers in preference order; empty = the manifest's
    order. Names are checked against the manifests when capabilities are resolved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: Toggle = "auto"
    prefer: tuple[str, ...] = ()

    _origins: dict[str, str] = PrivateAttr(default_factory=dict)  # field -> config layer

    def origin(self, *fields: str) -> str | None:
        """The layer(s) that set ``fields`` (all fields if none), e.g. ``env JARVIS_CAP_X``.

        Set by ``load_config()``; ``None`` for a ``CapabilityConfig`` built in code.
        """
        keys = fields or tuple(self._origins)
        found = sorted({self._origins[k] for k in keys if k in self._origins})
        return ", ".join(found) or None


class JarvisConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str | None = None
    hardware: HardwareConfig = HardwareConfig()
    backends: BackendSettings = BackendSettings()
    store: StoreSettings = StoreSettings()
    capabilities: dict[str, CapabilityConfig] = {}
    logging: LogSettings = LogSettings()
    # role -> catalogue model id (#56); runtime name -> where it is reached on this device
    models: dict[Role, str] = {}
    runtimes: dict[str, RuntimeConfig] = {}

    _sources: tuple[str, ...] = PrivateAttr(default=("defaults",))
    _resolved: BackendSettings | None = PrivateAttr(default=None)
    _set_by: dict[tuple[str, ...], str] = PrivateAttr(default_factory=dict)

    @field_validator("capabilities", mode="before")
    @classmethod
    def _shorthand(cls, value: Any) -> Any:
        """``vision = "off"`` is short for ``[capabilities.vision] enabled = "off"``."""
        if isinstance(value, dict):
            return {k: {"enabled": v} if isinstance(v, str) else v for k, v in value.items()}
        return value

    def set_by(self, *path: str) -> str | None:
        """The layer that set the value at ``path``, e.g. ``set_by("models", "llm")`` ->
        ``"env JARVIS_MODEL_LLM"``; ``None`` = a default (or a config built in code)."""
        return self._set_by.get(path)

    @property
    def sources(self) -> tuple[str, ...]:
        """The layers this config was built from, lowest precedence first."""
        return self._sources

    def backend_settings(self) -> BackendSettings:
        """For ``build_backends()``: ``backends`` with the ``[models]`` assignment applied.

        Raises ``ModelProblems`` if the assignment doesn't fit the catalogue;
        ``load_config()`` checks this up front and reports it as a ``ConfigError``.
        """
        if self._resolved is None:
            self._resolved = resolve_backends(
                self.models, self.runtimes, self.backends, load_catalogue()
            )
        return self._resolved

    def store_settings(self) -> StoreSettings:
        """For ``open_state()``."""
        return self.store
