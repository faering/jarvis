"""The voice loop: one actor task owns the state machine of docs/state-machine.md.

Every input (source events, finished turns, offloaded results, finished speech) goes
through one inbox and is handled in order, so state changes never race: only the actor
changes the state or emits events. The slow parts run beside it and report back through
the inbox:

- the *turn* task: STT, memory, routing, then streaming the local LLM into the
  ``SpeechQueue`` (hot) or asking the actor to offload (heavy). It posts its state changes
  and UI events tagged with its generation; the actor applies them in order and drops
  those of a turn superseded by a barge-in. A barge-in also cancels it.
- offloaded heavy tasks: their reply is spoken once no turn is being produced and the user
  is not mid-utterance, queued behind any speech still playing. At most ``max_offloads``
  are in flight (running or waiting to be spoken); past that, Jarvis says ``BUSY``.
- speech watchers: Speaking -> Idle once the queue has played everything.

A ``done`` event means the reply is complete: shown, and handed to the ``SpeechQueue``.
It says ``spoken=False`` if the queue refused the turn or dropped a chunk of it, or TTS or
playback of part of it had already failed by then; speech runs on after ``done``, so later
failures are only logged. Memory is best-effort: a store failure is logged and the reply
still completes (and ``done`` is still sent).

Each turn runs under a trace id (docs/logging.md): started by a ``Wake`` (continued by its
utterance) or an utterance, logged as ``turn started`` / ``turn finished`` and stamped on
every event of the turn. An offloaded reply is spoken later under its original id.
"""

import asyncio
import collections
import contextlib
import dataclasses
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from jarvis_agent.backends import STT, BackendError, ChatMessage
from jarvis_agent.logs import TRACE, kv, new_trace_id, reset_trace_id, set_trace_id
from jarvis_agent.loop.events import LoopEvent, LoopState, ReplyText, StateChanged, Transcript
from jarvis_agent.loop.source import AudioSource, Cancel, SourceEvent, Utterance, Wake
from jarvis_agent.routing import Reply, Route, Router, Task
from jarvis_agent.speech import SpeechQueue
from jarvis_agent.store import ConversationMemory, StoreError

log = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis, a handheld assistant. Your replies are spoken aloud: keep them short, "
    "plain and conversational."
)
CONTEXT_TURNS = 10  # recent conversation turns sent to the LLM
MAX_OFFLOADS = 4  # heavy tasks running or waiting to be spoken
MAX_INPUTS = 32  # utterances/wakes queued but not yet handled


class LoopBusy(Exception):
    """Too much input is already waiting; the caller should tell the user to retry."""


SORRY = "Sorry, I can't answer that right now."
BUSY = "I'm still working on your earlier requests. Please ask again in a moment."


@dataclass(frozen=True)
class _TurnDone:
    generation: int
    speech_turn: int | None  # the speech turn it produced, if any


@dataclass(frozen=True)
class _FromTurn:
    """A state change or UI event from the turn task, applied by the actor."""

    generation: int
    event: LoopEvent


@dataclass(frozen=True)
class _Offload:
    """The turn task routed heavy: the actor dispatches it (or says it is busy)."""

    generation: int
    messages: list[ChatMessage]


@dataclass(frozen=True)
class _Offloaded:
    handle: asyncio.Task[Reply]
    trace_id: str | None


@dataclass(frozen=True)
class _Trace:
    """The turn the actor is in: its trace id and when it started (monotonic)."""

    trace_id: str
    started: float


@dataclass(frozen=True)
class _SpeechDone:
    pass


type _Message = SourceEvent | _TurnDone | _FromTurn | _Offload | _Offloaded | _SpeechDone
type Listener = Callable[[LoopEvent], None]


class VoiceLoop:
    """Drives Idle -> Listening -> Routing -> Speaking / Offloaded; see the module docstring.

    Conversation turns are appended to ``memory``; the last ``context_turns`` of them are the
    LLM context (for the hot path also trimmed to the routing policy's ``max_hot_chars``).
    At most ``max_offloads`` heavy tasks are in flight (running, or finished and waiting to
    be spoken); a heavy utterance past that gets the spoken ``BUSY`` reply instead.
    """

    def __init__(
        self,
        router: Router,
        speech: SpeechQueue,
        stt: STT,
        memory: ConversationMemory,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        context_turns: int = CONTEXT_TURNS,
        max_offloads: int = MAX_OFFLOADS,
        max_inputs: int = MAX_INPUTS,
    ) -> None:
        if max_offloads < 1:
            raise ValueError("max_offloads must be >= 1")
        if max_inputs < 1:
            raise ValueError("max_inputs must be >= 1")
        self._router = router
        self._speech = speech
        self._stt = stt
        self._memory = memory
        self._system_prompt = system_prompt
        self._context_turns = context_turns
        self._max_offloads = max_offloads
        self._offloads = 0  # dispatched and not yet spoken (running or in _ready)
        self._max_inputs = max_inputs
        self._inputs = 0  # input events queued in _inbox, not yet handled

        self._inbox: asyncio.Queue[_Message] = asyncio.Queue()
        self._state = LoopState.IDLE
        self._generation = 0  # bumped by every barge-in: older turns are stale
        self._turn: asyncio.Task[None] | None = None
        # Finished heavy replies (None = failed) with their turn's trace id.
        self._ready: collections.deque[tuple[Reply | None, str | None]] = collections.deque()
        self._trace: _Trace | None = None
        self._listeners: list[Listener] = []
        self._runner: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- public ------------------------------------------------------------------------

    @property
    def state(self) -> LoopState:
        return self._state

    def start(self) -> None:
        if self._runner is not None:
            raise RuntimeError("VoiceLoop already started")
        self._runner = asyncio.create_task(self._run(), name="voice-loop")

    async def aclose(self) -> None:
        """Stop the loop, the current turn and any attached sources. Idempotent."""
        tasks = [task for task in (self._runner, self._turn) if task is not None]
        tasks += self._tasks
        self._runner, self._turn = None, None
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def submit(self, event: SourceEvent) -> None:
        """Feed one input event (never blocks). Raises ``LoopBusy`` when ``max_inputs``
        events are already waiting: input is bounded, internal messages are not."""
        if self._inputs >= self._max_inputs:
            raise LoopBusy(f"{self._inputs} inputs already waiting")
        self._inputs += 1
        self._inbox.put_nowait(event)

    def say(self, text: str, *, deep: bool = False, trace_id: str | None = None) -> None:
        """Text input: a complete utterance, as if spoken (under ``trace_id``, if given)."""
        self.submit(Utterance(text=text, deep=deep, trace_id=trace_id))

    def attach(self, source: AudioSource) -> None:
        """Consume ``source`` in the background until it ends or the loop closes."""
        self._spawn(self._pump(source), "voice-source")

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener`` (synchronously; it must not block) with every ``LoopEvent``.
        Returns the unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe

    # ---- the actor ---------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            message = await self._inbox.get()
            if isinstance(message, (Wake, Cancel, Utterance)):
                self._inputs -= 1
            try:
                await self._handle(message)
                await self._speak_ready()
            except Exception:
                log.exception(
                    "failed to handle a message", extra=kv(message=type(message).__name__)
                )

    async def _handle(self, message: _Message) -> None:
        match message:
            case Wake():
                await self._barge_in()
                self._begin(new_trace_id(), "wake_word")
                self._set(LoopState.LISTENING)
            case Cancel():
                if self._state is LoopState.LISTENING:
                    self._set(LoopState.IDLE, outcome="cancelled")
            case Utterance():
                # The utterance after a wake word continues that turn.
                woken = self._state is LoopState.LISTENING and message.trace_id is None
                await self._barge_in(keep=woken)
                if not (woken and self._trace):
                    source = "voice" if message.audio is not None else "say"
                    self._begin(message.trace_id or new_trace_id(), source)
                self._set(LoopState.LISTENING)
                self._set(LoopState.ROUTING)  # the utterance is the turn boundary
                self._turn = asyncio.create_task(
                    self._reply(message, self._generation), name="voice-turn"
                )
            case _FromTurn(generation, event):
                if generation != self._generation:
                    return  # superseded by a barge-in
                if isinstance(event, StateChanged):
                    self._set(event.state)
                else:
                    self._emit(event)
            case _Offload(generation, messages):
                if generation == self._generation:
                    self._offload(messages)
            case _TurnDone(generation, speech_turn):
                if generation != self._generation:
                    return  # superseded by a barge-in
                self._turn = None
                if speech_turn is not None:
                    self._watch(speech_turn)
                self._idle_if_silent()
            case _Offloaded(handle):
                if handle.cancelled():
                    self._offloads -= 1
                elif (error := handle.exception()) is not None:
                    token = set_trace_id(message.trace_id)
                    try:
                        log.error("offloaded task failed", exc_info=error)
                    finally:
                        reset_trace_id(token)
                    self._ready.append((None, message.trace_id))
                else:
                    self._ready.append((handle.result(), message.trace_id))
            case _SpeechDone():
                self._idle_if_silent()

    def _idle_if_silent(self) -> None:
        """Speaking -> Idle once no turn is being produced and nothing is left to play."""
        if self._state is LoopState.SPEAKING and self._turn is None and not self._speech.speaking:
            self._set(LoopState.IDLE)

    def _offload(self, messages: list[ChatMessage]) -> None:
        """Routing -> Offloaded -> Idle: dispatch a heavy task, unless too many are in flight
        (then say so at once rather than pile up unbounded work)."""
        if self._offloads >= self._max_offloads:
            log.warning("heavy tasks in flight, refusing another", extra=kv(count=self._offloads))
            turn, spoken = self._say_turn(BUSY)
            self._set(LoopState.SPEAKING)
            self._emit(ReplyText(text=BUSY, done=True, spoken=spoken))
            self._watch(turn)
            return
        self._set(LoopState.OFFLOADED)
        self._offloads += 1
        handle = self._router.offload(Task(messages, route=Route.HEAVY))
        trace_id = self._trace.trace_id if self._trace else None
        handle.add_done_callback(lambda done: self._inbox.put_nowait(_Offloaded(done, trace_id)))
        self._set(LoopState.IDLE, outcome="offloaded")  # dispatched: the loop stays responsive

    async def _barge_in(self, *, keep: bool = False) -> None:
        """A new turn wins: drop the reply being produced and silence speech. The current
        turn's trace ends, unless ``keep`` (the utterance of a wake-word turn)."""
        if self._trace is not None and not keep:
            self._finish("barged_in")
        self._generation += 1
        turn, self._turn = self._turn, None
        if turn is not None:
            turn.cancel()
            await asyncio.gather(turn, return_exceptions=True)
        if self._speech.speaking:
            await self._speech.interrupt()

    async def _speak_ready(self) -> None:
        """Offloaded -> Speaking: speak finished heavy replies, unless a turn is being
        produced or the user is talking (then they wait for the next chance)."""
        while (
            self._ready
            and self._turn is None
            and self._state not in (LoopState.LISTENING, LoopState.ROUTING)
        ):
            reply, trace_id = self._ready.popleft()
            self._offloads -= 1
            text, degraded = (SORRY, True) if reply is None else (reply.text, reply.degraded)
            turn, spoken = self._say_turn(text)  # queued behind speech still playing
            if self._trace is None and trace_id is not None:
                # The loop is free: its turn resumes, and Speaking -> Idle finishes it.
                self._trace = _Trace(trace_id, time.monotonic())
                set_trace_id(trace_id)
            # Stamped with its own turn's id, not the one the loop may be in now.
            self._set(LoopState.SPEAKING, trace_id=trace_id)
            if reply is not None:
                await self._remember(text)
            done = ReplyText(text=text, done=True, degraded=degraded, spoken=spoken)
            self._emit(dataclasses.replace(done, trace_id=trace_id))
            token = set_trace_id(trace_id)
            try:
                log.info("offloaded reply spoken", extra=kv(chars=len(text), degraded=degraded))
            finally:
                reset_trace_id(token)
            self._watch(turn)

    # ---- one turn ----------------------------------------------------------------------

    async def _reply(self, utterance: Utterance, generation: int) -> None:
        """The turn task. It never changes the state itself: state changes and events go
        through the inbox (``_post``), so the actor applies them in order."""
        speech_turn: int | None = None
        try:
            text = await self._transcribe(utterance)
            if not text:
                log.debug("nothing was said")
                self._post(generation, StateChanged(LoopState.IDLE))  # nothing was said
            else:
                self._post(generation, Transcript(text))
                await self._memory.append("user", text)
                # Route on the new utterance alone: a long conversation history must not
                # push every later turn onto the heavy route.
                user: list[ChatMessage] = [{"role": "user", "content": text}]
                route = self._router.route(Task(user, deep=utterance.deep))
                log.debug("routed", extra=kv(route=route.value, deep=utterance.deep))
                if route is Route.HEAVY:
                    messages = await self._context(budget=None)
                    self._inbox.put_nowait(_Offload(generation, messages))
                else:
                    budget = self._router.policy.max_hot_chars
                    speech_turn = await self._stream(generation, await self._context(budget))
        except asyncio.CancelledError:
            raise
        except Exception:  # STT, store or no local LLM: say so rather than go silent
            log.error("turn failed", exc_info=True)
            speech_turn, spoken = self._say_turn(SORRY)
            self._post(generation, StateChanged(LoopState.SPEAKING))
            self._post(generation, ReplyText(text=SORRY, done=True, spoken=spoken))
        self._inbox.put_nowait(_TurnDone(generation, speech_turn))

    async def _transcribe(self, utterance: Utterance) -> str:
        if utterance.text is not None:
            text = utterance.text.strip()
        else:
            assert utterance.audio is not None  # guaranteed by Utterance
            started = time.monotonic()
            audio, audio_format = utterance.audio, utterance.audio_format
            text = (await self._stt.transcribe(audio, audio_format=audio_format)).strip()
            log.debug("transcribed", extra=kv(duration_ms=_ms_since(started), chars=len(text)))
        log.log(TRACE, "heard text", extra=kv(text=text))  # user text: TRACE only
        return text

    async def _stream(self, generation: int, messages: list[ChatMessage]) -> int:
        """Hot path: stream the local LLM into speech as it generates."""
        llm = self._router.hot().backend
        assert llm is not None  # hot() only returns available providers
        turn, accepted = self._begin_turn()
        dropped = self._speech.dropped  # chunks the queue drops count as not spoken
        self._post(generation, StateChanged(LoopState.SPEAKING))
        parts: list[str] = []
        started = time.monotonic()
        try:
            async for delta in llm.stream(messages):
                if not parts:
                    log.debug("first token", extra=kv(latency_ms=_ms_since(started)))
                parts.append(delta)
                self._speech.feed(turn, delta)
                self._post(generation, ReplyText(delta=delta))
        except BackendError:
            log.error("local LLM failed", exc_info=True, extra=kv(chars=len("".join(parts))))
            if not parts:  # nothing said yet: apologise, and don't remember the apology
                self._speech.feed(turn, SORRY)
                self._speech.end_turn(turn)
                spoken = self._spoken(turn, accepted, dropped)
                self._post(generation, ReplyText(text=SORRY, done=True, spoken=spoken))
                return turn
            # Cut off mid-reply: what was already said is kept and remembered.
        self._speech.end_turn(turn)
        spoken = self._spoken(turn, accepted, dropped)
        text = "".join(parts)
        log.debug("reply streamed", extra=kv(duration_ms=_ms_since(started), chars=len(text)))
        log.log(TRACE, "reply text", extra=kv(text=text))
        await self._remember(text)  # best-effort: done is sent even if this fails
        self._post(generation, ReplyText(text=text, done=True, spoken=spoken))
        return turn

    async def _context(self, budget: int | None) -> list[ChatMessage]:
        """System prompt + the recent turns (the new utterance is the last one)."""
        turns = await self._memory.recent(self._context_turns)
        history: list[ChatMessage] = [{"role": t.role, "content": t.content} for t in turns]
        if budget is not None:
            history = _fit(history, budget)
        if not self._system_prompt:
            return history
        return [{"role": "system", "content": self._system_prompt}, *history]

    # ---- helpers -----------------------------------------------------------------------

    async def _remember(self, reply: str) -> None:
        """Store an assistant turn, best-effort: a store failure is logged and must not cut
        the reply short (stores raise ``StoreError``; ``SqliteStore`` wraps sqlite3 errors)."""
        try:
            await self._memory.append("assistant", reply)
        except StoreError:
            log.error("could not store the reply", exc_info=True)

    def _post(self, generation: int, event: LoopEvent) -> None:
        """From the turn task: have the actor apply ``event`` (see ``_FromTurn``)."""
        self._inbox.put_nowait(_FromTurn(generation, event))

    def _begin_turn(self) -> tuple[int, bool]:
        """``SpeechQueue.begin_turn`` plus whether it was accepted: past ``max_turns`` the
        queue refuses the turn (counting it in ``dropped_turns``) and ignores its text."""
        dropped = self._speech.dropped_turns
        turn = self._speech.begin_turn()
        return turn, self._speech.dropped_turns == dropped

    def _say_turn(self, text: str) -> tuple[int, bool]:
        """Speak ``text`` as its own turn; returns the turn id and ``spoken`` (``_spoken``)."""
        turn, accepted = self._begin_turn()
        dropped = self._speech.dropped
        self._speech.feed(turn, text)
        self._speech.end_turn(turn)
        return turn, self._spoken(turn, accepted, dropped)

    def _spoken(self, turn: int, accepted: bool, dropped: int) -> bool:
        """``spoken`` for a done frame, as known now: the turn was accepted, none of its
        chunks were dropped (``dropped`` = the queue's count when it began), and no TTS or
        playback of it has failed yet. Call it right after ``end_turn``, before awaiting:
        the turn is then still in flight, so ``has_failed`` still knows about it."""
        return accepted and self._speech.dropped == dropped and not self._speech.has_failed(turn)

    def _watch(self, speech_turn: int) -> None:
        async def watch() -> None:
            await self._speech.wait(speech_turn)
            self._inbox.put_nowait(_SpeechDone())

        self._spawn(watch(), "voice-speech-watch")

    async def _pump(self, source: AudioSource) -> None:
        async for event in source.events():
            try:
                self.submit(event)
            except LoopBusy:
                log.warning(
                    "input backlog full, dropped an event", extra=kv(event=type(event).__name__)
                )

    def _spawn(self, work: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(work, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _begin(self, trace_id: str, source: str) -> None:
        """Start a turn's trace. The actor's context holds its id, so the turn task and
        offloaded work (created from it) log under it too."""
        self._trace = _Trace(trace_id, time.monotonic())
        set_trace_id(trace_id)
        log.info("turn started", extra=kv(trace_id=trace_id, source=source))

    def _finish(self, outcome: str) -> None:
        if self._trace is None:
            return
        duration_ms = _ms_since(self._trace.started)
        log.info("turn finished", extra=kv(duration_ms=duration_ms, outcome=outcome))
        self._trace = None
        set_trace_id(None)

    def _set(self, state: LoopState, *, trace_id: str | None = None, outcome: str = "done") -> None:
        """Change the state. Back to Idle ends the current turn's trace (``outcome``), after
        its Idle event. ``trace_id`` stamps the event with another turn's id."""
        if state is not self._state:
            self._state = state
            self._emit(StateChanged(state, trace_id=trace_id))
        if state is LoopState.IDLE:
            self._finish(outcome)

    def _emit(self, event: LoopEvent) -> None:
        if event.trace_id is None and self._trace is not None:
            event = dataclasses.replace(event, trace_id=self._trace.trace_id)
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                log.exception("listener failed")


def _ms_since(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _fit(history: list[ChatMessage], budget: int) -> list[ChatMessage]:
    """Drop the oldest turns until the total fits ``budget`` chars (keeping the last one)."""
    total = sum(len(message["content"]) for message in history)
    start = 0
    while total > budget and start < len(history) - 1:
        total -= len(history[start]["content"])
        start += 1
    return history[start:]
