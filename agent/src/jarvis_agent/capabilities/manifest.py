"""Capability manifests: what a user-facing ability needs, and who can provide it.

A capability ("voice", "vision", "notes") declares ``Requirements`` on the layers below it:
**hardware** (probed), **backends** (model roles), **tools** (MCP, #68) and **state** (store
domains). Each ``ProviderSpec`` adds its own requirements on top; the first satisfiable
provider in preference order wins.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from jarvis_agent.hardware import HARDWARE
from jarvis_agent.routing import ComputeLayer

BACKEND_ROLES = ("llm", "stt", "tts", "heavy_llm", "vision")
STATE_DOMAINS = ("notes", "todo", "calendar", "kv", "memory", "notifications")
Kind = Literal["hardware", "backend", "tool", "state"]
Source = Literal["local", "faelab"]


@dataclass(frozen=True)
class Requirements:
    hardware: frozenset[str] = frozenset()
    backends: frozenset[str] = frozenset()
    tools: frozenset[str] = frozenset()  # MCP tool names; free-form until #68
    state: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for kind, names, known in (
            ("hardware", self.hardware, HARDWARE),
            ("backends", self.backends, BACKEND_ROLES),
            ("state", self.state, STATE_DOMAINS),
        ):
            if unknown := sorted(set(names) - set(known)):
                raise ValueError(f"unknown {kind}: {', '.join(unknown)}")

    def items(self) -> Iterable[tuple[Kind, str]]:
        """Every requirement as ``(kind, name)``, in a stable order."""
        yield from (("hardware", n) for n in sorted(self.hardware))
        yield from (("backend", n) for n in sorted(self.backends))
        yield from (("tool", n) for n in sorted(self.tools))
        yield from (("state", n) for n in sorted(self.state))


def requires(
    *,
    hardware: Iterable[str] = (),
    backends: Iterable[str] = (),
    tools: Iterable[str] = (),
    state: Iterable[str] = (),
) -> Requirements:
    return Requirements(
        frozenset(hardware), frozenset(backends), frozenset(tools), frozenset(state)
    )


@dataclass(frozen=True)
class ProviderSpec:
    """One way to deliver a capability: where it runs and what it needs beyond the base."""

    name: str
    layer: ComputeLayer
    source: Source = "local"  # local = in this agent; faelab = the home server, over MCP
    requires: Requirements = Requirements()


@dataclass(frozen=True)
class Manifest:
    name: str
    description: str
    providers: tuple[ProviderSpec, ...]  # default preference order
    requires: Requirements = field(default_factory=Requirements)

    def __post_init__(self) -> None:
        names = [p.name for p in self.providers]
        if not names or len(names) != len(set(names)):
            raise ValueError(f"{self.name}: needs one or more uniquely named providers")

    def provider(self, name: str) -> ProviderSpec | None:
        return next((p for p in self.providers if p.name == name), None)
