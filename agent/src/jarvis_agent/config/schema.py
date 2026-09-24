"""The validated agent config: hardware toggles, role backends, state store, capabilities.

Backends and store reuse ``BackendSettings`` / ``StoreSettings`` as-is, so the layered
config feeds ``build_backends()`` and ``open_state()`` unchanged.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator

from jarvis_agent.backends.config import BackendSettings
from jarvis_agent.hardware import Toggle
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


class JarvisConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: str | None = None
    hardware: HardwareConfig = HardwareConfig()
    backends: BackendSettings = BackendSettings()
    store: StoreSettings = StoreSettings()
    capabilities: dict[str, CapabilityConfig] = {}

    _sources: tuple[str, ...] = PrivateAttr(default=("defaults",))

    @field_validator("capabilities", mode="before")
    @classmethod
    def _shorthand(cls, value: Any) -> Any:
        """``vision = "off"`` is short for ``[capabilities.vision] enabled = "off"``."""
        if isinstance(value, dict):
            return {k: {"enabled": v} if isinstance(v, str) else v for k, v in value.items()}
        return value

    @property
    def sources(self) -> tuple[str, ...]:
        """The layers this config was built from, lowest precedence first."""
        return self._sources

    def backend_settings(self) -> BackendSettings:
        """For ``build_backends()``."""
        return self.backends

    def store_settings(self) -> StoreSettings:
        """For ``open_state()``."""
        return self.store
