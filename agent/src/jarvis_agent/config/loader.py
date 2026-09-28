"""Build the config from layers, later wins: defaults -> profile -> local file -> env.

- **profile**: ``profiles/<name>.toml`` in this package, picked by ``JARVIS_PROFILE`` or the
  local file's ``profile`` key (env wins). None = defaults only.
- **local file**: the TOML file at ``JARVIS_CONFIG`` (e.g. ``/data/jarvis.toml``); unset =
  none. Set but missing is an error, not a silent skip.
- **env**: the existing ``JARVIS_*`` names (see ``ENV_KEYS``), plus
  ``JARVIS_HW_<NAME>=on|off|auto``, ``JARVIS_CAP_<NAME>=on|off|auto``,
  ``JARVIS_MODEL_<ROLE>=<catalogue id>`` and ``JARVIS_RUNTIME_<NAME>_URL`` /
  ``JARVIS_RUNTIME_<NAME>_API_KEY``. Empty = unset, so a copied ``.env.example`` changes
  nothing.

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
from jarvis_agent.models import ModelProblems

type Leaves = dict[tuple[str, ...], tuple[Any, str]]  # path -> (value, source)

# Env names (backends.config, store.config, logging) -> config path. Lower-cased values.
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
    "JARVIS_LOG_DIR": ("logging", "dir"),
    "JARVIS_LOG_LEVEL": ("logging", "level"),
}
ENV_PREFIXES = {"JARVIS_HW_": "hardware", "JARVIS_CAP_": "capabilities", "JARVIS_MODEL_": "models"}
RUNTIME_ENV = {"_URL": "base_url", "_API_KEY": "api_key"}  # JARVIS_RUNTIME_<NAME><suffix>
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
    try:
        config.backend_settings()  # the [models] assignment against the catalogue
    except ModelProblems as exc:
        raise ConfigError(
            [
                f"models.{role}: {msg}" + _from(merged, ("models", role))
                for role, msg in exc.problems.items()
            ]
        ) from None
    config._sources = tuple(sources)
    config._set_by = {path: src for path, (_, src) in merged.items()}
    for cap, cfg in config.capabilities.items():  # so later checks can name the layer
        cfg._origins = {  # "" = the table itself, when it was given empty
            path[2] if len(path) > 2 else "": src
            for path, (_, src) in merged.items()
            if path[:2] == ("capabilities", cap)
        }
    return config


def _read_toml(path: Path, problems: list[str]) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        problems.append(f"{path}: file not found")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
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
        if var.startswith("JARVIS_RUNTIME_"):
            name = var.removeprefix("JARVIS_RUNTIME_")
            for suffix, field in RUNTIME_ENV.items():
                if name.endswith(suffix) and len(name) > len(suffix):
                    runtime = name.removesuffix(suffix).lower()
                    leaves[("runtimes", runtime, field)] = (value, f"env {var}")
            continue
        for prefix, section in ENV_PREFIXES.items():
            if var.startswith(prefix) and len(var) > len(prefix):
                key = var.removeprefix(prefix).lower()
                if section == "models":  # a model id: case kept
                    leaves[(section, key)] = (value, f"env {var}")
                    continue
                path = (section, key) if section == "hardware" else (section, key, "enabled")
                leaves[path] = (value.lower(), f"env {var}")
    return leaves


def _flatten(data: Mapping[str, Any], source: str, prefix: tuple[str, ...] = ()) -> Leaves:
    leaves: Leaves = {}
    for key, value in data.items():
        path = (*prefix, key)
        if prefix == ("capabilities",) and isinstance(value, str):
            value = {"enabled": value}  # shorthand, so it merges with a table elsewhere
        if isinstance(value, dict) and value:
            leaves |= _flatten(value, source, path)
        else:  # an empty table is a leaf too, so a bare `[capabilities.x]` still gets checked
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
            # An empty table only marks presence: it keeps what lower layers set below it.
            if leaf[0] == {} and any(len(p) > len(path) and _related(p, path) for p in merged):
                continue
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


def _from(merged: Leaves, path: tuple[str, ...]) -> str:
    return f" (from {merged[path][1]})" if path in merged else ""


def _describe(err: Any, merged: Leaves) -> str:
    loc = tuple(str(part) for part in err["loc"])
    where = ".".join(loc) or "config"
    sources = sorted({src for path, (_, src) in merged.items() if loc and _related(path, loc)})
    msg = err["msg"].removeprefix("Value error, ")
    return f"{where}: {msg}" + (f" (from {', '.join(sources)})" if sources else "")
