"""The router: hot-path LLM selection, async heavy dispatch and graceful fallback.

- Hot path: the first available local LLM, NPU before CPU. Callers stream from it.
- Heavy: ``offload()`` returns an ``asyncio.Task`` at once and the reply arrives later (the
  Offloaded -> Speaking transition). If the heavy LLM is not configured, fails or times out,
  the local LLM answers instead and the reply is marked ``degraded``.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from jarvis_agent.backends import LLM, BackendError, Backends, ChatMessage, Vision
from jarvis_agent.routing.layers import ComputeLayer, NoProviderError, Provider, pick
from jarvis_agent.routing.policy import Route, RoutingPolicy, Task

log = logging.getLogger(__name__)

HOT_LAYERS = (ComputeLayer.NPU, ComputeLayer.CPU)
HEAVY_LAYERS = (ComputeLayer.REMOTE,)
VISION_LAYERS = (ComputeLayer.CAMERA, ComputeLayer.NPU, ComputeLayer.CPU)

# Matches the HTTP read timeout, but bounds the whole heavy call rather than one read.
HEAVY_TIMEOUT = 120.0


@dataclass(frozen=True)
class Reply:
    text: str
    route: Route  # the route the policy chose
    provider: str  # who actually answered
    layer: ComputeLayer
    degraded: bool = False  # the heavy LLM was wanted, but the local one answered
    reason: str | None = None  # why it degraded


class Router:
    def __init__(
        self,
        llms: Sequence[Provider[LLM]],
        vision: Sequence[Provider[Vision]] = (),
        *,
        policy: RoutingPolicy | None = None,
        heavy_timeout: float = HEAVY_TIMEOUT,
    ) -> None:
        self._llms = list(llms)
        self._vision = list(vision)
        self.policy = policy or RoutingPolicy()
        self.heavy_timeout = heavy_timeout
        self._pending: set[asyncio.Task[Reply]] = set()

    def route(self, task: Task) -> Route:
        return self.policy.decide(task)

    def hot(self) -> Provider[LLM]:
        """The local LLM for the hot path (``NoProviderError`` if there is none)."""
        return pick(self._llms, HOT_LAYERS)

    def vision(self) -> Provider[Vision]:
        return pick(self._vision, VISION_LAYERS)

    async def answer(self, task: Task) -> Reply:
        """Answer ``task`` on its route. Awaits heavy work: the voice loop uses ``offload``."""
        if self.route(task) is Route.HEAVY:
            return await self._heavy(task.messages)
        return await self._local(task.messages, Route.HOT)

    def offload(self, task: Task) -> asyncio.Task[Reply]:
        """Start the heavy route in the background and return its handle immediately."""
        handle = asyncio.create_task(self._heavy(task.messages), name="jarvis-heavy")
        self._pending.add(handle)  # hold a reference until it finishes
        handle.add_done_callback(self._pending.discard)
        return handle

    @property
    def pending(self) -> int:
        """Offloaded tasks still running."""
        return len(self._pending)

    async def aclose(self) -> None:
        """Cancel offloaded work that is still running."""
        pending = list(self._pending)
        for handle in pending:
            handle.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _heavy(self, messages: list[ChatMessage]) -> Reply:
        try:
            provider = pick(self._llms, HEAVY_LAYERS)
        except NoProviderError:
            return await self._local(messages, Route.HEAVY, "heavy LLM not configured")
        assert provider.backend is not None  # pick() only returns available providers
        try:
            async with asyncio.timeout(self.heavy_timeout):
                text = await provider.backend.chat(messages)
        except TimeoutError:
            reason = f"{provider.name} timed out after {self.heavy_timeout:g}s"
        except BackendError as exc:
            reason = f"{provider.name} failed: {exc}"
        else:
            return Reply(text, Route.HEAVY, provider.name, provider.layer)
        log.warning("heavy route degraded to the local LLM: %s", reason)
        return await self._local(messages, Route.HEAVY, reason)

    async def _local(
        self, messages: list[ChatMessage], route: Route, degraded: str | None = None
    ) -> Reply:
        provider = self.hot()
        assert provider.backend is not None
        text = await provider.backend.chat(messages)
        return Reply(text, route, provider.name, provider.layer, degraded is not None, degraded)


def build_router(backends: Backends, *, policy: RoutingPolicy | None = None) -> Router:
    """Place the configured backends on their layers. Pi-only slots stay empty for now."""
    llms: list[Provider[LLM]] = [
        Provider("hailo", ComputeLayer.NPU),  # on-NPU LLM (#60)
        Provider("llm", ComputeLayer.CPU, backends.llm),
        Provider("heavy_llm", ComputeLayer.REMOTE, backends.heavy_llm),
    ]
    vision: list[Provider[Vision]] = [
        Provider("imx500", ComputeLayer.CAMERA),  # on-sensor inference (#34, #35)
        Provider("hailo", ComputeLayer.NPU),  # (#60)
        Provider("vision", ComputeLayer.CPU, backends.vision),
    ]
    return Router(llms, vision, policy=policy)
