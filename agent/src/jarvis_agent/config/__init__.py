"""Layered agent config: defaults -> profile preset -> local file -> env vars.

``load_config()`` returns a validated ``JarvisConfig`` or raises one ``ConfigError`` that
lists every problem. Its ``backend_settings()`` / ``store_settings()`` feed
``build_backends()`` / ``open_state()`` unchanged. ``python -m jarvis_agent.config`` prints
the resolved config (secrets masked) and the capability report.
"""

from jarvis_agent.config.loader import (
    ENV_KEYS,
    ConfigError,
    available_profiles,
    load_config,
    profiles_dir,
)
from jarvis_agent.config.schema import CapabilityConfig, HardwareConfig, JarvisConfig

__all__ = [
    "ENV_KEYS",
    "CapabilityConfig",
    "ConfigError",
    "HardwareConfig",
    "JarvisConfig",
    "available_profiles",
    "load_config",
    "profiles_dir",
]
