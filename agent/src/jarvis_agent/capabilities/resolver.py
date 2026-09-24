"""Resolve capabilities at startup: which are enabled, by which provider, and why not.

Never raises for an unsatisfiable capability: it is disabled with a reason (for logs, the
CLI, and later the LLM's self-description, #74). Only config that names an unknown
capability or provider is an error (``ConfigError``), like any other invalid config.
"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from jarvis_agent.capabilities.builtin import BUILTIN
from jarvis_agent.capabilities.manifest import Kind, Manifest, ProviderSpec
from jarvis_agent.config import CapabilityConfig, ConfigError, JarvisConfig
from jarvis_agent.hardware import HardwareStatus
from jarvis_agent.store.config import DOMAINS

log = logging.getLogger(__name__)

ALWAYS_LOCAL_STATE = ("kv", "memory", "notifications")  # Jarvis-owned (ADR 0005)


@dataclass(frozen=True)
class Available:
    """What the lower layers offer. ``missing`` explains absent names, keyed ``kind:name``."""

    hardware: frozenset[str] = frozenset()
    backends: frozenset[str] = frozenset()
    tools: frozenset[str] = frozenset()
    state: frozenset[str] = frozenset()
    missing: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(
        cls,
        config: JarvisConfig,
        hardware: Mapping[str, HardwareStatus],
        tools: Iterable[str] = (),
    ) -> Available:
        """Mirror what ``build_backends()`` / ``open_state()`` will build from ``config``.

        Mock backends count as available (they are the dev default); vision is always the
        mock until real ones land (#35, #60). ``tools`` comes from MCP discovery (#68).
        """
        why = {f"hardware:{n}": s.reason for n, s in hardware.items() if not s.present}
        backends = {"llm", "stt", "tts", "vision"}
        if config.backends.heavy_llm.backend != "none":
            backends.add("heavy_llm")
        else:
            why["backend:heavy_llm"] = "not configured"
        state = set(ALWAYS_LOCAL_STATE)
        for domain in DOMAINS:
            if (where := getattr(config.store, domain)) == "local":
                state.add(domain)
            else:
                why[f"state:{domain}"] = f"served by {where}"
        return cls(
            hardware=frozenset(n for n, s in hardware.items() if s.present),
            backends=frozenset(backends),
            tools=frozenset(tools),
            state=frozenset(state),
            missing=why,
        )

    def has(self, kind: Kind, name: str) -> bool:
        pool = {
            "hardware": self.hardware,
            "backend": self.backends,
            "tool": self.tools,
            "state": self.state,
        }
        return name in pool[kind]

    def explain(self, kind: Kind, name: str) -> str:
        return f"{kind} {name} ({self.missing.get(f'{kind}:{name}', 'not available')})"


@dataclass(frozen=True)
class Enabled:
    name: str
    provider: ProviderSpec


@dataclass(frozen=True)
class Disabled:
    name: str
    reason: str
    required: bool = False  # configured ``on``, yet unsatisfiable


@dataclass(frozen=True)
class CapabilityReport:
    enabled: dict[str, Enabled]
    disabled: dict[str, Disabled]

    @property
    def required_unmet(self) -> list[Disabled]:
        return [d for d in self.disabled.values() if d.required]


def check_config(
    settings: Mapping[str, CapabilityConfig], manifests: Sequence[Manifest] = BUILTIN
) -> list[str]:
    """Problems with the ``capabilities`` config section: unknown names or providers."""
    known = {m.name: m for m in manifests}
    problems = []
    for name, cfg in settings.items():
        if (manifest := known.get(name)) is None:
            problems.append(
                f"capabilities.{name}: unknown capability (known: {', '.join(sorted(known))})"
            )
            continue
        if bad := [p for p in cfg.prefer if manifest.provider(p) is None]:
            problems.append(
                f"capabilities.{name}.prefer: unknown provider {', '.join(bad)} "
                f"(known: {', '.join(p.name for p in manifest.providers)})"
            )
    return problems


def resolve(
    available: Available,
    settings: Mapping[str, CapabilityConfig] | None = None,
    manifests: Sequence[Manifest] = BUILTIN,
) -> CapabilityReport:
    """Pick each capability's first satisfiable provider, in configured preference order."""
    settings = settings or {}
    if problems := check_config(settings, manifests):
        raise ConfigError(problems)
    enabled: dict[str, Enabled] = {}
    disabled: dict[str, Disabled] = {}
    for manifest in manifests:
        cfg = settings.get(manifest.name, CapabilityConfig())
        outcome = _resolve_one(manifest, cfg, available)
        if isinstance(outcome, Enabled):
            enabled[manifest.name] = outcome
            continue
        disabled[manifest.name] = outcome
        if outcome.required:
            log.warning("capability %s is on but unavailable: %s", manifest.name, outcome.reason)
        else:
            log.info("capability %s disabled: %s", manifest.name, outcome.reason)
    return CapabilityReport(enabled, disabled)


def _resolve_one(
    manifest: Manifest, cfg: CapabilityConfig, available: Available
) -> Enabled | Disabled:
    if cfg.enabled == "off":
        return Disabled(manifest.name, "off in config")
    required = cfg.enabled == "on"
    if base := _unmet(manifest.requires.items(), available):
        return Disabled(manifest.name, "missing " + ", ".join(base), required)
    order = cfg.prefer or tuple(p.name for p in manifest.providers)
    tried = []
    for name in order:
        provider = manifest.provider(name)
        assert provider is not None  # check_config
        if not (unmet := _unmet(provider.requires.items(), available)):
            return Enabled(manifest.name, provider)
        tried.append(f"{name}: missing {', '.join(unmet)}")
    return Disabled(manifest.name, "no provider available (" + "; ".join(tried) + ")", required)


def _unmet(reqs: Iterable[tuple[Kind, str]], available: Available) -> list[str]:
    return [available.explain(kind, name) for kind, name in reqs if not available.has(kind, name)]
