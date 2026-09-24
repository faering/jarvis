"""Three-compute-layer routing: pick a layer per request, keep heavy work off the hot path.

``build_router(backends)`` places the role backends on layers (camera, NPU, CPU, remote).
``Router`` chooses hot vs heavy with ``RoutingPolicy`` and falls back when a layer is
missing or failing. See docs/architecture.md (Compute layers).
"""

from jarvis_agent.routing.layers import ComputeLayer, NoProviderError, Provider, pick
from jarvis_agent.routing.policy import Route, RoutingPolicy, Task
from jarvis_agent.routing.router import Reply, Router, build_router

__all__ = [
    "ComputeLayer",
    "NoProviderError",
    "Provider",
    "Reply",
    "Route",
    "Router",
    "RoutingPolicy",
    "Task",
    "build_router",
    "pick",
]
