"""Capabilities: user-facing abilities composed from hardware, backends, tools and state.

Layering (each only looks down): hardware (``jarvis_agent.hardware``, probed) -> backends
(``jarvis_agent.backends``) -> capabilities (this package) -> tools (MCP, #68). At startup:

    config = load_config()
    hardware = detect(config.hardware.model_dump())
    report = resolve(Available.from_config(config, hardware), config.capabilities)
"""

from jarvis_agent.capabilities.builtin import BUILTIN
from jarvis_agent.capabilities.manifest import (
    BACKEND_ROLES,
    STATE_DOMAINS,
    Manifest,
    ProviderSpec,
    Requirements,
    requires,
)
from jarvis_agent.capabilities.resolver import (
    Available,
    CapabilityReport,
    Disabled,
    Enabled,
    check_config,
    resolve,
)

__all__ = [
    "BACKEND_ROLES",
    "BUILTIN",
    "STATE_DOMAINS",
    "Available",
    "CapabilityReport",
    "Disabled",
    "Enabled",
    "Manifest",
    "ProviderSpec",
    "Requirements",
    "check_config",
    "requires",
    "resolve",
]
