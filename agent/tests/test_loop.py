"""The voice loop: state transitions, hot streaming, offload, degradation, barge-in, memory.

Fakes are gated by events instead of sleeps; timeouts only guard against hangs.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest

from jarvis_agent.backends import LLM, BackendError, ChatMessage
from jarvis_agent.backends.mock import MockSTT
from jarvis_agent.loop import (
    Cancel,
    LoopEvent,
    LoopState,
    ReplyText,
    ScriptedSource,
    StateChanged,
    Transcript,
    Utterance,
    VoiceLoop,
    Wake,
)
from jarvis_agent.loop.voice import DEFAULT_SYSTEM_PROMPT, SORRY, _fit
from jarvis_agent.routing import ComputeLayer, Provider, Reply, Router, Task
from jarvis_agent.speech import SpeechQueue
from jarvis_agent.store import State, StoreSettings, open_state

pytestmark = pytest.mark.anyio

IDLE, LISTENING, ROUTING, SPEAKING, OFFLOADED = (
    LoopState.IDLE,
    LoopState.LISTENING,
    LoopState.ROUTING,
    LoopState.SPEAKING,
    LoopState.OFFLOADED,
)


class ScriptLLM:
    """Streams ``chunks`` (``chat`` returns them joined) and records every prompt. A chunk
    listed in ``gates`` is held until ``release(chunk)``."""

    def __init__(self, *replies: Sequence[str], gates: set[str] | None = None) -> None:
        self.replies = [list(reply) for reply in replies] or [["local answer"]]
        self.prompts: list[list[ChatMessage]] = []
        self.cancelled = False
        self._gates = {chunk: asyncio.Event() for chunk in gates or ()}

    def release(self, chunk: str) -> None:
        self._gates[chunk].set()

    def _next(self, messages: list[ChatMessage]) -> list[str]:
        self.prompts.append(messages)
        return self.replies[min(len(self.prompts), len(self.replies)) - 1]

    async def chat(self, messages: list[ChatMessage]) -> str:
        return "".join(self._next(messages))

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for chunk in self._next(messages):
            if gate := self._gates.get(chunk):
                try:
                    await gate.wait()
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
            yield chunk


class GatedLLM:
    """A heavy model that answers only once ``gate`` is set."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.prompts: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage]) -> str:
        self.prompts.append(messages)
        await self.gate.wait()
        return "heavy answer"

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        yield await self.chat(messages)


class FailingLLM:
    async def chat(self, messages: list[ChatMessage]) -> str:
        raise BackendError("llm", "HTTP 503", status_code=503)

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        raise BackendError("llm", "HTTP 503", status_code=503)
        yield ""  # pragma: no cover - makes this an async generator


class TextTTS:
    async def synthesize(self, text: str) -> bytes:
        return text.encode()


class Sink:
    """Records playback. With ``hold=True`` each play waits until ``stop()``."""

    def __init__(self, hold: bool = False) -> None:
        self.hold = hold
        self.played: list[bytes] = []
        self.stops = 0
        self._stop = asyncio.Event()
        self._played = asyncio.Event()

    async def until_played(self, wav: bytes, timeout: float = 2.0) -> None:
        async with asyncio.timeout(timeout):
            while self.played[-1:] != [wav]:
                self._played.clear()
                await self._played.wait()

    async def play(self, wav: bytes) -> None:
        self.played.append(wav)
        self._played.set()
        if self.hold:
            await self._stop.wait()

    async def stop(self) -> None:
        self.stops += 1
        self._stop.set()
        self._stop = asyncio.Event()


class Recorder:
    def __init__(self) -> None:
        self.events: list[LoopEvent] = []
        self._changed = asyncio.Event()

    def __call__(self, event: LoopEvent) -> None:
        self.events.append(event)
        self._changed.set()

    @property
    def states(self) -> list[LoopState]:
        return [e.state for e in self.events if isinstance(e, StateChanged)]

    @property
    def replies(self) -> list[ReplyText]:
        return [e for e in self.events if isinstance(e, ReplyText) and e.done]

    async def until(self, predicate: Callable[[], bool], timeout: float = 2.0) -> None:
        async with asyncio.timeout(timeout):
            while not predicate():
                self._changed.clear()
                await self._changed.wait()

    async def until_idle_after(self, replies: int) -> None:
        """Wait for the ``replies``-th finished reply and the return to Idle after it."""
        await self.until(lambda: len(self.replies) >= replies and self.states[-1] is IDLE)


@dataclass
class Harness:
    loop: VoiceLoop
    events: Recorder
    router: Router
    state: State
    sink: Sink
    handles: list[asyncio.Task[Reply]]

    async def memory(self) -> list[tuple[str, str]]:
        return [(turn.role, turn.content) for turn in await self.state.memory.recent()]


@asynccontextmanager
async def running(
    llm: LLM, heavy: LLM | None = None, *, sink: Sink | None = None, stt: MockSTT | None = None
) -> AsyncIterator[Harness]:
    state = await open_state(StoreSettings(db=":memory:"))
    router = Router(
        [
            Provider("local", ComputeLayer.CPU, llm),
            Provider("heavy", ComputeLayer.REMOTE, heavy),
        ]
    )
    handles: list[asyncio.Task[Reply]] = []
    offload = router.offload

    def spy(task: Task) -> asyncio.Task[Reply]:
        handles.append(offload(task))
        return handles[-1]

    router.offload = spy  # type: ignore[method-assign]
    sink = sink or Sink()
    speech = SpeechQueue(TextTTS(), sink)
    speech.start()
    loop = VoiceLoop(router, speech, stt or MockSTT(), state.memory)
    events = Recorder()
    loop.subscribe(events)
    loop.start()
    try:
        yield Harness(loop, events, router, state, sink, handles)
    finally:
        await loop.aclose()
        await router.aclose()
        await speech.aclose()
        await state.aclose()


async def test_hot_reply_streams_into_speech() -> None:
    llm = ScriptLLM(["Hello there. ", "How are ", "you?"])
    async with running(llm) as h:
        h.loop.say("hi")
        await h.events.until_idle_after(1)

        assert h.events.states == [LISTENING, ROUTING, SPEAKING, IDLE]
        assert h.events.events[2] == Transcript("hi")
        deltas = [e.delta for e in h.events.events if isinstance(e, ReplyText) and not e.done]
        assert deltas == ["Hello there. ", "How are ", "you?"]
        assert h.events.replies == [ReplyText(text="Hello there. How are you?", done=True)]
        assert h.sink.played == [b"Hello there.", b"How are you?"]
        assert h.handles == []  # never offloaded
        assert await h.memory() == [("user", "hi"), ("assistant", "Hello there. How are you?")]


async def test_audio_source_goes_through_stt() -> None:
    source = ScriptedSource([Wake(), Utterance(audio=b"RIFF...")])
    async with running(ScriptLLM(["ok"]), stt=MockSTT("what time is it")) as h:
        h.loop.attach(source)
        await h.events.until_idle_after(1)

        assert h.events.states == [LISTENING, ROUTING, SPEAKING, IDLE]
        assert Transcript("what time is it") in h.events.events


async def test_cancel_returns_to_idle() -> None:
    async with running(ScriptLLM()) as h:
        h.loop.submit(Wake())
        h.loop.submit(Cancel())
        await h.events.until(lambda: h.events.states == [LISTENING, IDLE])
        assert h.loop.state is IDLE


async def test_empty_transcript_returns_to_idle_silently() -> None:
    async with running(ScriptLLM(), stt=MockSTT("  ")) as h:
        h.loop.submit(Utterance(audio=b"noise"))
        await h.events.until(lambda: h.events.states == [LISTENING, ROUTING, IDLE])
        assert h.events.replies == []
        assert await h.memory() == []


async def test_heavy_task_is_offloaded_and_spoken_when_ready() -> None:
    heavy = GatedLLM()
    async with running(ScriptLLM(["quick answer"]), heavy) as h:
        h.loop.say("plan my week", deep=True)
        await h.events.until(lambda: h.events.states == [LISTENING, ROUTING, OFFLOADED, IDLE])
        assert h.events.replies == []

        # The loop stays responsive while the heavy task runs.
        h.loop.say("what time is it")
        await h.events.until_idle_after(1)
        assert h.events.replies[0].text == "quick answer"

        heavy.gate.set()
        await h.events.until_idle_after(2)
        assert h.events.replies[1] == ReplyText(text="heavy answer", done=True, degraded=False)
        assert h.sink.played[-1] == b"heavy answer"
        assert h.events.states[-2:] == [SPEAKING, IDLE]
        assert heavy.prompts[0] == [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": "plan my week"},
        ]
        assert ("assistant", "heavy answer") in await h.memory()


async def test_heavy_failure_degrades_to_the_local_model() -> None:
    async with running(ScriptLLM(["local answer"]), FailingLLM()) as h:
        h.loop.say("plan my week", deep=True)
        await h.events.until_idle_after(1)

        assert h.events.replies == [ReplyText(text="local answer", done=True, degraded=True)]
        assert h.sink.played == [b"local answer"]


async def test_heavy_result_waits_while_the_user_is_talking() -> None:
    heavy = GatedLLM()
    async with running(ScriptLLM(), heavy) as h:
        h.loop.say("plan my week", deep=True)
        await h.events.until(lambda: h.events.states[-1:] == [IDLE])
        h.loop.submit(Wake())
        await h.events.until(lambda: h.events.states[-1:] == [LISTENING])

        heavy.gate.set()
        await h.handles[0]  # the result is in the inbox now; the user is still talking
        h.loop.submit(Cancel())
        await h.events.until_idle_after(1)

        assert h.events.states[-4:] == [LISTENING, IDLE, SPEAKING, IDLE]
        assert h.events.replies[0].text == "heavy answer"


async def test_barge_in_interrupts_speech_and_the_reply() -> None:
    llm = ScriptLLM(["First sentence. ", "never"], ["Second."], gates={"never"})
    sink = Sink(hold=True)
    async with running(llm, sink=sink) as h:
        h.loop.say("one")
        await sink.until_played(b"First sentence.")

        h.loop.say("two")
        await h.events.until(lambda: len(h.events.replies) == 1)

        assert llm.cancelled
        assert sink.stops >= 1
        assert h.events.states == [LISTENING, ROUTING, SPEAKING, LISTENING, ROUTING, SPEAKING]
        assert h.events.replies == [ReplyText(text="Second.", done=True)]
        await sink.until_played(b"Second.")
        # The interrupted reply is not remembered.
        assert await h.memory() == [("user", "one"), ("user", "two"), ("assistant", "Second.")]


async def test_memory_is_persisted_and_used_as_context() -> None:
    llm = ScriptLLM(["Hi Ada."], ["Your name is Ada."])
    async with running(llm) as h:
        h.loop.say("my name is Ada")
        await h.events.until_idle_after(1)
        h.loop.say("what is my name")
        await h.events.until_idle_after(2)

        assert llm.prompts[1] == [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": "my name is Ada"},
            {"role": "assistant", "content": "Hi Ada."},
            {"role": "user", "content": "what is my name"},
        ]
        assert await h.memory() == [
            ("user", "my name is Ada"),
            ("assistant", "Hi Ada."),
            ("user", "what is my name"),
            ("assistant", "Your name is Ada."),
        ]


async def test_local_failure_says_sorry_and_is_not_remembered() -> None:
    async with running(FailingLLM()) as h:
        h.loop.say("hi")
        await h.events.until_idle_after(1)

        assert h.events.replies == [ReplyText(text=SORRY, done=True)]
        assert h.sink.played == [SORRY.encode()]
        assert await h.memory() == [("user", "hi")]


def test_hot_context_is_trimmed_oldest_first() -> None:
    history: list[ChatMessage] = [
        {"role": "user", "content": "a" * 10},
        {"role": "assistant", "content": "b" * 10},
        {"role": "user", "content": "c" * 10},
    ]
    assert _fit(history, 20) == history[1:]
    assert _fit(history, 5) == history[2:]  # the new utterance always stays
    assert _fit(history, 30) == history
