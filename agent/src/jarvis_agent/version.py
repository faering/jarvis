"""Build provenance of the running agent (AGENTS.md "Build provenance & displayed versions").

The Docker build bakes the values from ``scripts/version.sh agent`` into the image as
``JARVIS_VERSION`` (canonical SemVer), ``JARVIS_REVISION`` (full commit sha) and
``JARVIS_BUILD_TIME`` (RFC 3339, UTC). Outside such a build they are unset (or empty, as
docker compose passes them) and we fall back to the installed package version.
"""

import os
from collections.abc import Mapping
from typing import TypedDict

from jarvis_agent import __version__


class BuildInfo(TypedDict):
    version: str
    revision: str
    dirty: bool
    build_time: str | None


def build_info(env: Mapping[str, str] = os.environ) -> BuildInfo:
    """Current build provenance; empty variables count as unset."""
    version = env.get("JARVIS_VERSION") or __version__
    return {
        "version": version,
        "revision": env.get("JARVIS_REVISION") or "unknown",
        # scripts/version.sh marks a dirty tree with a trailing ".dirty" build identifier.
        "dirty": version.endswith(".dirty"),
        "build_time": env.get("JARVIS_BUILD_TIME") or None,
    }
