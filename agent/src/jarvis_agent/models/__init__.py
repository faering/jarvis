"""The model catalogue: every model Jarvis knows, and which one fills each role here.

See ``catalogue.toml`` for the data and ``resolve_backends()`` for how a device's
``[models]`` / ``[runtimes]`` config becomes backend settings (#56, ADR 0012).
"""

from jarvis_agent.models.catalogue import (
    ROLES,
    WIRED,
    Catalogue,
    ModelEntry,
    ModelProblems,
    Role,
    RuntimeConfig,
    load_catalogue,
    resolve_backends,
)

__all__ = [
    "ROLES",
    "WIRED",
    "Catalogue",
    "ModelEntry",
    "ModelProblems",
    "Role",
    "RuntimeConfig",
    "load_catalogue",
    "resolve_backends",
]
