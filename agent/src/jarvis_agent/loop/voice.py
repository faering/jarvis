"""The voice loop: one actor task owns the state machine of docs/state-machine.md.

Every input (source events, finished turns, offloaded results, finished speech) goes
through one inbox and is handled in order, so state changes never race. The slow parts run
beside it and report back through the inbox:

- the *turn* task: STT, memory, routing, then streaming the local LLM into the
  ``SpeechQueue`` (hot) or ``router.offload()`` (heavy). A barge-in cancels it.
- offloaded heavy tasks: their reply is spoken once no turn is being produced and the user
  is not mid-utterance, queued behind any speech still playing.
- speech watchers: Speaking -> Idle once the queue has played everything.
"""

import asyncio
import collections
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from jarvis_agent.backends import STT, BackendError, ChatMessage
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
SORRY = "Sorry, I can't answer that right now."


@dataclass(frozen=True)
class _TurnDone:
    generation: int
    speech_turn: int | None  # the speech turn it produced, if any


@dataclass(frozen=True)
class _Offloaded:
    handle: asyncio.Task[Reply]


@dataclass(frozen=True)
class _SpeechDone:
    pass


type _Message = SourceEvent | _TurnDone | _Offloaded | _SpeechDone
type Listener = Callable[[LoopEvent], None]


class VoiceLoop:
    """Drives Idle -> Listening -> Routing -> Speaking / Offloaded; see the module docstring.

    Conversation turns are appended to ``memory``; the last ``context_turns`` of them are the
    LLM context (for the hot path also trimmed to the routing policy's ``max_hot_chars``).
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
    ) -> None:
        self._router = router
        self._speech = speech
        self._stt = stt
        self._memory = memory
        self._system_prompt = system_prompt
        self._context_turns = context_turns

        self._inbox: asyncio.Queue[_Message] = asyncio.Queue()
        self._state = LoopState.IDLE
        self._generation = 0  # bumped by every barge-in: older turns are stale
        self._turn: asyncio.Task[None] | None = None
        self._ready: collections.deque[Reply | None] = collections.deque()  # None = failed
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
        """Feed one input event (never blocks)."""
        self._inbox.put_nowait(event)

    def say(self, text: str, *, deep: bool = False) -> None:
        """Text input: a complete utterance, as if spoken."""
        self.submit(Utterance(text=text, deep=deep))

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
            try:
                await self._handle(message)
                await self._speak_ready()
            except Exception:
                log.exception("voice loop: failed to handle %r", message)

    async def _handle(self, message: _Message) -> None:
        match message:
            case Wake():
                await self._barge_in()
                self._set(LoopState.LISTENING)
            case Cancel():
                if self._state is LoopState.LISTENING:
                    self._set(LoopState.IDLE)
            case Utterance():
                await self._barge_in()
                self._set(LoopState.LISTENING)
                self._set(LoopState.ROUTING)  # the utterance is the turn boundary
                self._turn = asyncio.create_task(
                    self._reply(message, self._generation), name="voice-turn"
                )
            case _TurnDone(generation, speech_turn):
                if generation != self._generation:
                    return  # superseded by a barge-in
                self._turn = None
                if speech_turn is not None:
                    self._watch(speech_turn)
            case _Offloaded(handle):
                if not handle.cancelled():
                    if (error := handle.exception()) is not None:
                        log.error("voice loop: offloaded task failed: %s", error)
                        self._ready.append(None)
                    else:
                        self._ready.append(handle.result())
            case _SpeechDone():
                if (
                    self._state is LoopState.SPEAKING
                    and self._turn is None
                    and not self._speech.speaking
                ):
                    self._set(LoopState.IDLE)

    async def _barge_in(self) -> None:
        """A new turn wins: drop the reply being produced and silence speech."""
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
            reply = self._ready.popleft()
            text, degraded = (SORRY, True) if reply is None else (reply.text, reply.degraded)
            turn = self._speech.say(text)  # queued behind speech still playing
            self._set(LoopState.SPEAKING)
            if reply is not None:
                await self._remember(text)
            self._emit(ReplyText(text=text, done=True, degraded=degraded))
            self._watch(turn)

    # ---- one turn ----------------------------------------------------------------------

    async def _reply(self, utterance: Utterance, generation: int) -> None:
        speech_turn: int | None = None
        try:
            text = await self._transcribe(utterance)
            if not text:
                self._set(LoopState.IDLE)  # nothing was said
            else:
                self._emit(Transcript(text))
                await self._memory.append("user", text)
                # Route on the new utterance alone: a long conversation history must not
                # push every later turn onto the heavy route.
                user: list[ChatMessage] = [{"role": "user", "content": text}]
                if self._router.route(Task(user, deep=utterance.deep)) is Route.HEAVY:
                    self._offload(await self._context(budget=None))
                else:
                    budget = self._router.policy.max_hot_chars
                    speech_turn = await self._stream(await self._context(budget))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # STT, store or no local LLM: say so rather than go silent
            log.error("voice loop: turn failed: %s", exc)
            speech_turn = self._speech.say(SORRY)
            self._set(LoopState.SPEAKING)
            self._emit(ReplyText(text=SORRY, done=True))
        self._inbox.put_nowait(_TurnDone(generation, speech_turn))

    async def _transcribe(self, utterance: Utterance) -> str:
        if utterance.text is not None:
            return utterance.text.strip()
        assert utterance.audio is not None  # guaranteed by Utterance
        text = await self._stt.transcribe(utterance.audio, audio_format=utterance.audio_format)
        return text.strip()

    def _offload(self, messages: list[ChatMessage]) -> None:
        self._set(LoopState.OFFLOADED)
        handle = self._router.offload(Task(messages, route=Route.HEAVY))
        handle.add_done_callback(lambda done: self._inbox.put_nowait(_Offloaded(done)))
        self._set(LoopState.IDLE)  # dispatched: the loop stays responsive

    async def _stream(self, messages: list[ChatMessage]) -> int:
        """Hot path: stream the local LLM into speech as it generates."""
        llm = self._router.hot().backend
        assert llm is not None  # hot() only returns available providers
        turn = self._speech.begin_turn()
        self._set(LoopState.SPEAKING)
        parts: list[str] = []
        failed = False
        try:
            async for delta in llm.stream(messages):
                parts.append(delta)
                self._speech.feed(turn, delta)
                self._emit(ReplyText(delta=delta))
        except BackendError as exc:
            log.error("voice loop: local LLM failed: %s", exc)
            failed = True
            if not parts:
                parts.append(SORRY)
                self._speech.feed(turn, SORRY)
        self._speech.end_turn(turn)
        text = "".join(parts)
        if not failed:
            await self._remember(text)
        self._emit(ReplyText(text=text, done=True))  # done = spoken (queued) and remembered
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
        """Store an assistant turn; a store failure must not cut the reply short."""
        try:
            await self._memory.append("assistant", reply)
        except StoreError as exc:
            log.error("voice loop: could not store the reply: %s", exc)

    def _watch(self, speech_turn: int) -> None:
        async def watch() -> None:
            await self._speech.wait(speech_turn)
            self._inbox.put_nowait(_SpeechDone())

        self._spawn(watch(), "voice-speech-watch")

    async def _pump(self, source: AudioSource) -> None:
        async for event in source.events():
            self.submit(event)

    def _spawn(self, work: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(work, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _set(self, state: LoopState) -> None:
        if state is not self._state:
            self._state = state
            self._emit(StateChanged(state))

    def _emit(self, event: LoopEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                log.exception("voice loop: listener failed")


def _fit(history: list[ChatMessage], budget: int) -> list[ChatMessage]:
    """Drop the oldest turns until the total fits ``budget`` chars (keeping the last one)."""
    total = sum(len(message["content"]) for message in history)
    start = 0
    while total > budget and start < len(history) - 1:
        total -= len(history[start]["content"])
        start += 1
    return history[start:]
