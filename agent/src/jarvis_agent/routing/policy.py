"""Hot vs heavy: a small, explicit routing policy (no model in the loop yet).

Rules, first match wins:

1. The caller's explicit ``Task.route``.
2. ``Task.deep`` (the caller wants deeper reasoning) -> heavy.
3. The prompt is longer than ``max_hot_chars`` -> heavy (a 1-4B model has a small context
   and slows down on long prompts).
4. Otherwise -> hot.
"""

from dataclasses import dataclass
from enum import StrEnum

from jarvis_agent.backends import ChatMessage


class Route(StrEnum):
    HOT = "hot"  # local small LLM, latency-critical (the voice loop)
    HEAVY = "heavy"  # heavy LLM, async and off the hot path


@dataclass(frozen=True)
class Task:
    messages: list[ChatMessage]
    route: Route | None = None  # explicit choice; overrides the heuristics
    deep: bool = False  # e.g. planning, long-form answers


@dataclass(frozen=True)
class RoutingPolicy:
    # ~1k tokens: beyond this a 1-4B model on the Pi gets noticeably slow.
    max_hot_chars: int = 4_000

    def decide(self, task: Task) -> Route:
        if task.route is not None:
            return task.route
        if task.deep:
            return Route.HEAVY
        if sum(len(message["content"]) for message in task.messages) > self.max_hot_chars:
            return Route.HEAVY
        return Route.HOT
