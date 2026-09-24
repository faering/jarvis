"""Compute-layer routing: policy, layer fallback, async heavy dispatch and degradation."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from jarvis_agent.backends import (
    LLM,
    BackendError,
    BackendSettings,
    ChatMessage,
    HeavyRoleSettings,
    build_backends,
)
from jarvis_agent.backends.mock import MockLLM, MockVision
from jarvis_agent.routing import (
    ComputeLayer,
    NoProviderError,
    Provider,
    Route,
    Router,
    RoutingPolicy,
    Task,
    build_router,
    pick,
)

MESSAGES: list[ChatMessage] = [{"role": "user", "content": "plan my week"}]


class GatedLLM:
    """Answers only once ``gate`` is set, so tests control when heavy work finishes."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.calls = 0

    async def chat(self, messages: list[ChatMessage]) -> str:
        self.calls += 1
        await self.gate.wait()
        return "heavy answer"

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        yield await self.chat(messages)


class FailingLLM:
    async def chat(self, messages: list[ChatMessage]) -> str:
        raise BackendError("llm", "HTTP 503", status_code=503)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        yield await self.chat(messages)


def _router(heavy: LLM | None, *, heavy_timeout: float = 5.0) -> Router:
    return Router(
        [
            Provider("hailo", ComputeLayer.NPU),
            Provider("local", ComputeLayer.CPU, MockLLM()),
            Provider("heavy", ComputeLayer.REMOTE, heavy),
        ],
        heavy_timeout=heavy_timeout,
    )


# ---- policy -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (Task(MESSAGES), Route.HOT),
        (Task(MESSAGES, deep=True), Route.HEAVY),
        (Task([{"role": "user", "content": "x" * 101}]), Route.HEAVY),
        (Task([{"role": "user", "content": "x" * 100}]), Route.HOT),
        (Task(MESSAGES, route=Route.HEAVY), Route.HEAVY),
        (Task(MESSAGES, route=Route.HOT, deep=True), Route.HOT),  # explicit wins
    ],
)
def test_policy_decides_hot_or_heavy(task: Task, expected: Route) -> None:
    assert RoutingPolicy(max_hot_chars=100).decide(task) is expected


def test_default_policy_keeps_short_turns_hot() -> None:
    assert _router(None).route(Task(MESSAGES)) is Route.HOT


# ---- layers -----------------------------------------------------------------


def test_pick_falls_through_unavailable_layers() -> None:
    providers = [
        Provider("hailo", ComputeLayer.NPU),
        Provider("cpu", ComputeLayer.CPU, "cpu-backend"),
    ]
    chosen = pick(providers, [ComputeLayer.NPU, ComputeLayer.CPU])
    assert (chosen.name, chosen.layer) == ("cpu", ComputeLayer.CPU)


def test_pick_prefers_the_earlier_layer_when_available() -> None:
    providers = [
        Provider("cpu", ComputeLayer.CPU, "cpu-backend"),
        Provider("hailo", ComputeLayer.NPU, "npu-backend"),
    ]
    assert pick(providers, [ComputeLayer.NPU, ComputeLayer.CPU]).name == "hailo"


def test_pick_raises_when_nothing_is_available() -> None:
    with pytest.raises(NoProviderError):
        pick([Provider[str]("hailo", ComputeLayer.NPU)], [ComputeLayer.NPU])


def test_off_device_router_uses_cpu_for_hot_path_and_vision() -> None:
    router = build_router(build_backends(BackendSettings()))
    assert router.hot().layer is ComputeLayer.CPU
    vision = router.vision()
    assert (vision.layer, type(vision.backend)) == (ComputeLayer.CPU, MockVision)


# ---- answering --------------------------------------------------------------


@pytest.mark.anyio
async def test_hot_task_is_answered_locally() -> None:
    reply = await _router(GatedLLM()).answer(Task(MESSAGES))
    assert (reply.text, reply.route, reply.layer) == (
        "mock reply to: plan my week",
        Route.HOT,
        ComputeLayer.CPU,
    )
    assert not reply.degraded


@pytest.mark.anyio
async def test_heavy_task_uses_the_heavy_llm() -> None:
    heavy = GatedLLM()
    heavy.gate.set()
    reply = await _router(heavy).answer(Task(MESSAGES, deep=True))
    assert (reply.text, reply.provider, reply.layer) == ("heavy answer", "heavy", "remote")
    assert not reply.degraded


@pytest.mark.anyio
async def test_offload_returns_immediately_and_the_result_arrives_later() -> None:
    heavy = GatedLLM()
    router = _router(heavy)

    handle = router.offload(Task(MESSAGES, deep=True))
    assert not handle.done()
    await asyncio.sleep(0)  # let it start; it now waits on the heavy LLM
    assert (heavy.calls, handle.done(), router.pending) == (1, False, 1)

    heavy.gate.set()
    reply = await handle
    assert (reply.text, reply.route, reply.degraded) == ("heavy answer", Route.HEAVY, False)
    assert router.pending == 0


@pytest.mark.anyio
async def test_unconfigured_heavy_falls_back_to_local_degraded() -> None:
    reply = await _router(None).offload(Task(MESSAGES))
    assert (reply.text, reply.layer, reply.route) == (
        "mock reply to: plan my week",
        ComputeLayer.CPU,
        Route.HEAVY,
    )
    assert reply.degraded
    assert reply.reason == "heavy LLM not configured"


@pytest.mark.anyio
async def test_heavy_error_falls_back_to_local_degraded() -> None:
    reply = await _router(FailingLLM()).answer(Task(MESSAGES, deep=True))
    assert (reply.provider, reply.degraded) == ("local", True)
    assert reply.reason is not None and "HTTP 503" in reply.reason


@pytest.mark.anyio
async def test_heavy_timeout_falls_back_to_local_degraded() -> None:
    reply = await _router(GatedLLM(), heavy_timeout=0.01).offload(Task(MESSAGES))
    assert (reply.provider, reply.degraded) == ("local", True)
    assert reply.reason == "heavy timed out after 0.01s"


@pytest.mark.anyio
async def test_cancelled_offload_does_not_fall_back() -> None:
    router = _router(GatedLLM())
    handle = router.offload(Task(MESSAGES))
    await asyncio.sleep(0)

    handle.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handle
    assert router.pending == 0


@pytest.mark.anyio
async def test_aclose_cancels_pending_offloads() -> None:
    router = _router(GatedLLM())
    handle = router.offload(Task(MESSAGES))
    await asyncio.sleep(0)

    await router.aclose()
    assert handle.cancelled()
    assert router.pending == 0


@pytest.mark.anyio
async def test_mock_heavy_backend_is_wired_through_the_factory() -> None:
    settings = BackendSettings(heavy_llm=HeavyRoleSettings(backend="mock"))
    reply = await build_router(build_backends(settings)).offload(Task(MESSAGES))
    assert (reply.text, reply.provider, reply.degraded) == (
        "mock heavy reply to: plan my week",
        "heavy_llm",
        False,
    )
