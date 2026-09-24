"""Build the config from layers, later wins: defaults -> profile -> local file -> env.

- **profile**: ``profiles/<name>.toml`` in this package, picked by ``JARVIS_PROFILE`` or the
  local file's ``profile`` key (env wins). None = defaults only.
- **local file**: the TOML file at ``JARVIS_CONFIG`` (e.g. ``/data/jarvis.toml``); unset =
  none. Set but missing is an error, not a silent skip.
- **env**: the existing ``JARVIS_*`` names (see ``ENV_KEYS``), plus
  ``JARVIS_HW_<NAME>=on|off|auto`` and ``JARVIS_CAP_<NAME>=on|off|auto``. Empty = unset,
  so a copied ``.env.example`` changes nothing.

Tables merge key by key; any other value (including lists) replaces the lower layer's.
Every problem found is collected into one ``ConfigError``.
"""

import os
import tomllib
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from jarvis_agent.config.schema import JarvisConfig

type Leaves = dict[tuple[str, ...], tuple[Any, str]]  # path -> (value, source)

# Existing env names (backends.config, store.config) -> config path. Lower-cased values.
ENV_KEYS: dict[str, tuple[str, ...]] = {
    f"JARVIS_{role.upper()}_{field.upper()}": ("backends", role, field)
    for role in ("llm", "stt", "tts", "heavy_llm")
    for field in ("backend", "base_url", "model", "api_key")
} | {
    "JARVIS_TTS_VOICE": ("backends", "tts", "voice"),
    "JARVIS_STATE_DB": ("store", "db"),
    "JARVIS_NOTES_PROVIDER": ("store", "notes"),
    "JARVIS_TODO_PROVIDER": ("store", "todo"),
    "JARVIS_CALENDAR_PROVIDER": ("store", "calendar"),
}
ENV_PREFIXES = {"JARVIS_HW_": "hardware", "JARVIS_CAP_": "capabilities"}
LOWERCASE = {"backend", "notes", "todo", "calendar"}


class ConfigError(ValueError):
    """The config is invalid; ``problems`` lists every issue found."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("invalid Jarvis config:\n" + "\n".join(f"  - {p}" for p in problems))


def profiles_dir() -> Path:
    return Path(str(resources.files("jarvis_agent.config") / "profiles"))


def available_profiles(directory: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (directory or profiles_dir()).glob("*.toml"))


def load_config(
    environ: Mapping[str, str] | None = None, *, profiles: Path | None = None
) -> JarvisConfig:
    """Resolve the layered config, or raise ``ConfigError`` listing every problem."""
    env = os.environ if environ is None else environ
    profiles = profiles or profiles_dir()
    problems: list[str] = []
    sources = ["defaults"]
    layers: list[Leaves] = []

    local: dict[str, Any] = {}
    if path := env.get("JARVIS_CONFIG", "").strip():
        local = _read_toml(Path(path), problems)

    name = env.get("JARVIS_PROFILE", "").strip().lower() or local.get("profile")
    if name is not None and not isinstance(name, str):
        problems.append(f"profile: must be a string, got {name!r}")
        name = None
    if name:
        known = available_profiles(profiles)
        if name in known:
            preset = _read_toml(profiles / f"{name}.toml", problems)
            preset.pop("profile", None)
            layers.append(_flatten(preset, f"profile {name}"))
            sources.append(f"profile {name}")
        else:
            problems.append(f"profile: unknown profile {name!r} (known: {', '.join(known)})")
    if local:
        layers.append(_flatten(local, f"file {path}"))
        sources.append(f"file {path}")
    if env_layer := _env_leaves(env):
        layers.append(env_layer)
        sources.append("env")
    if problems:  # unreadable layers: validating a partial merge would only add noise
        raise ConfigError(problems)

    merged = _merge(layers)
    data = _unflatten(merged)
    if name:
        data["profile"] = name
    try:
        config = JarvisConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError([_describe(err, merged) for err in exc.errors()]) from None
    config._sources = tuple(sources)
    return config


def _read_toml(path: Path, problems: list[str]) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        problems.append(f"{path}: file not found")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        problems.append(f"{path}: {exc}")
    return {}


def _env_leaves(env: Mapping[str, str]) -> Leaves:
    leaves: Leaves = {}
    for var, raw in env.items():
        value = raw.strip()
        if not value:
            continue
        if var in ENV_KEYS:
            path = ENV_KEYS[var]
            leaves[path] = (value.lower() if path[-1] in LOWERCASE else value, f"env {var}")
            continue
        for prefix, section in ENV_PREFIXES.items():
            if var.startswith(prefix) and len(var) > len(prefix):
                key = var.removeprefix(prefix).lower()
                path = (section, key) if section == "hardware" else (section, key, "enabled")
                leaves[path] = (value.lower(), f"env {var}")
    return leaves


def _flatten(data: Mapping[str, Any], source: str, prefix: tuple[str, ...] = ()) -> Leaves:
    leaves: Leaves = {}
    for key, value in data.items():
        path = (*prefix, key)
        if prefix == ("capabilities",) and isinstance(value, str):
            value = {"enabled": value}  # shorthand, so it merges with a table elsewhere
        if isinstance(value, dict):  # an empty table adds nothing, like in any merge
            leaves |= _flatten(value, source, path)
        else:
            leaves[path] = (value, source)
    return leaves


def _related(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """One path is the other, or lies above or below it."""
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def _merge(layers: list[Leaves]) -> Leaves:
    merged: Leaves = {}
    for layer in layers:
        for path, leaf in layer.items():
            # A later value replaces whatever the lower layers had at, above or below it.
            for old in [p for p in merged if _related(p, path)]:
                del merged[old]
            merged[path] = leaf
    return merged


def _unflatten(leaves: Leaves) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for path, (value, _) in leaves.items():
        node = root
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return root


def _describe(err: Any, merged: Leaves) -> str:
    loc = tuple(str(part) for part in err["loc"])
    where = ".".join(loc) or "config"
    sources = sorted({src for path, (_, src) in merged.items() if loc and _related(path, loc)})
    msg = err["msg"].removeprefix("Value error, ")
    return f"{where}: {msg}" + (f" (from {', '.join(sources)})" if sources else "")
