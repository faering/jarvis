"""Producer/consumer speech output with turn-boundary interrupts (barge-in).

Producers call the synchronous ``begin_turn`` / ``feed`` / ``end_turn`` / ``say``; they never
await TTS or playback, so the voice loop stays on the hot path. Two background stages run
the pipeline: *synth* turns pending text chunks into WAV, *play* sends them to the sink.
While one chunk plays, up to ``lookahead`` following chunks are synthesized ahead.

Every chunk carries its turn id. ``interrupt()`` marks all issued turns stale, drops their
queued chunks, cancels in-flight synthesis/playback and calls ``sink.stop()``; both stages
re-check staleness before acting, so an interrupted chunk never plays.
"""

import asyncio
import collections
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Self

from jarvis_agent.backends.base import TTS
from jarvis_agent.speech.segmenter import Segmenter
from jarvis_agent.speech.sink import AudioSink

logger = logging.getLogger(__name__)

type SpeechEventKind = Literal["started", "finished", "interrupted"]


@dataclass(frozen=True)
class SpeechEvent:
    """``started``: a turn's first audio began. ``finished``: all of it played.
    ``interrupted``: it was cut off (or dropped before playing) by ``interrupt()``."""

    kind: SpeechEventKind
    turn: int


@dataclass(frozen=True)
class _Chunk:
    turn: int
    text: str | None  # None marks the end of the turn


@dataclass(frozen=True)
class _Audio:
    turn: int
    wav: bytes | None  # None marks the end of the turn


class SpeechQueue:
    """Speaks reply text without blocking the caller; see the module docstring.

    Backpressure: at most ``max_pending`` text chunks wait for synthesis. Enqueueing never
    blocks — when full, the new chunk is dropped and logged (``dropped`` counts them). That
    many unspoken sentences means a runaway producer, and stalling the loop would be worse.

    Turns are bounded the same way: at most ``max_turns`` turns are in flight (queued,
    synthesizing or playing). ``begin_turn`` past that limit refuses the *new* turn — it
    gets an id, is reported ``interrupted`` at once, ``wait()`` on it returns immediately
    and its text is ignored (``dropped_turns`` counts them). So end-of-turn markers, which
    are never dropped on their own, stay bounded too. Dropping the newest (rather than
    evicting an older queued turn) matches the chunk policy and needs no extra staleness
    tracking; a caller that wants the fresh turn to win calls ``interrupt()`` first.
    """

    def __init__(
        self,
        tts: TTS,
        sink: AudioSink,
        *,
        on_event: Callable[[SpeechEvent], None] | None = None,
        max_pending: int = 64,
        max_turns: int = 16,
        lookahead: int = 1,
        segmenter: Callable[[], Segmenter] = Segmenter,
    ) -> None:
        if max_pending < 1 or max_turns < 1 or lookahead < 1:
            raise ValueError("max_pending, max_turns and lookahead must be >= 1")
        self._tts = tts
        self._sink = sink
        self._on_event = on_event
        self._max_pending = max_pending
        self._max_turns = max_turns
        self._new_segmenter = segmenter

        self._pending: collections.deque[_Chunk] = collections.deque()
        self._pending_texts = 0
        self._wake = asyncio.Event()
        self._ready: asyncio.Queue[_Audio] = asyncio.Queue(maxsize=lookahead)

        self._last_turn = 0  # ids are 1, 2, ...
        self._stale_upto = 0  # turns <= this were interrupted
        self._open_turn: int | None = None  # the turn still accepting text
        self._segmenter = segmenter()
        self._done: dict[int, asyncio.Event] = {}  # issued, not yet finished/interrupted
        self._started: set[int] = set()

        self._synth_op: asyncio.Task[bytes] | None = None
        self._play_op: asyncio.Task[None] | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self.dropped = 0
        self.dropped_turns = 0

    # ---- lifecycle ---------------------------------------------------------------------

    def start(self) -> None:
        if self._tasks:
            raise RuntimeError("SpeechQueue already started")
        self._tasks = [
            asyncio.create_task(self._synth_loop(), name="speech-synth"),
            asyncio.create_task(self._play_loop(), name="speech-play"),
        ]

    async def aclose(self) -> None:
        """Stop speaking, drop everything and cancel the pipeline. Idempotent."""
        # Also when never started: turns accepted before start() must still end, or their
        # wait() would hang. Once cleaned up, a second call does nothing.
        if self._tasks or self.speaking:
            await self.interrupt()
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self) -> Self:
        self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---- producer side (synchronous: never blocks the loop) -----------------------------

    def begin_turn(self) -> int:
        """Open a new turn and return its id. An open previous turn is ended (it still plays
        in order); use ``interrupt()`` first to cut it off instead. If ``max_turns`` turns
        are already in flight, the new turn is refused: reported ``interrupted`` right away
        and its text ignored."""
        if self._open_turn is not None:
            self.end_turn(self._open_turn)
        self._last_turn += 1
        turn = self._last_turn
        if len(self._done) >= self._max_turns:
            self.dropped_turns += 1
            logger.warning("speech: too many turns queued, dropped turn %d", turn)
            self._emit("interrupted", turn)
            return turn
        self._open_turn = turn
        self._segmenter = self._new_segmenter()
        self._done[turn] = asyncio.Event()
        return turn

    def feed(self, turn: int, text: str) -> None:
        """Add streamed reply text to ``turn``. Ignored if the turn is closed or stale, so a
        producer that lost a race with ``interrupt()`` cannot leak speech."""
        if turn != self._open_turn:
            return
        for chunk in self._segmenter.push(text):
            self._enqueue(_Chunk(turn, chunk))

    def end_turn(self, turn: int) -> None:
        """No more text for ``turn``: speak the remainder, then report it ``finished``."""
        if turn != self._open_turn:
            return
        for chunk in self._segmenter.flush():
            self._enqueue(_Chunk(turn, chunk))
        self._enqueue(_Chunk(turn, None))
        self._open_turn = None

    def say(self, text: str) -> int:
        """Speak a whole reply as its own turn; returns the turn id."""
        turn = self.begin_turn()
        self.feed(turn, text)
        self.end_turn(turn)
        return turn

    async def interrupt(self) -> None:
        """Barge-in / turn boundary: silence now and drop every issued turn."""
        self._stale_upto = self._last_turn
        self._open_turn = None
        self._segmenter.reset()
        self._pending.clear()
        self._pending_texts = 0
        while not self._ready.empty():
            self._ready.get_nowait()
        for op in (self._synth_op, self._play_op):
            if op is not None:
                op.cancel()
        cut, self._done = self._done, {}
        self._started.clear()
        for turn, done in cut.items():
            done.set()
            self._emit("interrupted", turn)
        try:
            await self._sink.stop()
        except Exception:
            logger.exception("speech: sink.stop() failed")

    async def wait(self, turn: int) -> None:
        """Wait until ``turn`` has finished or been interrupted."""
        if done := self._done.get(turn):
            await done.wait()

    @property
    def speaking(self) -> bool:
        """True while any turn is queued, being synthesized or playing."""
        return bool(self._done)

    # ---- consumer side -----------------------------------------------------------------

    def _enqueue(self, chunk: _Chunk) -> None:
        if chunk.text is not None:
            if self._pending_texts >= self._max_pending:
                self.dropped += 1
                logger.warning("speech: queue full, dropped chunk of turn %d", chunk.turn)
                return
            self._pending_texts += 1
        self._pending.append(chunk)
        self._wake.set()

    def _stale(self, turn: int) -> bool:
        return turn <= self._stale_upto

    async def _next_chunk(self) -> _Chunk:
        while not self._pending:
            self._wake.clear()
            await self._wake.wait()
        chunk = self._pending.popleft()
        if chunk.text is not None:
            self._pending_texts -= 1
        return chunk

    async def _synth_loop(self) -> None:
        while True:
            chunk = await self._next_chunk()
            if self._stale(chunk.turn):
                continue
            if chunk.text is None:
                await self._ready.put(_Audio(chunk.turn, None))
                continue
            self._synth_op = asyncio.ensure_future(self._tts.synthesize(chunk.text))
            wav = await _settle(self._synth_op, "tts.synthesize")
            self._synth_op = None
            if wav is not None and not self._stale(chunk.turn):
                await self._ready.put(_Audio(chunk.turn, wav))

    async def _play_loop(self) -> None:
        while True:
            audio = await self._ready.get()
            if self._stale(audio.turn):
                continue
            if audio.wav is None:
                self._finish(audio.turn)
                continue
            if audio.turn not in self._started:
                self._started.add(audio.turn)
                self._emit("started", audio.turn)
            self._play_op = asyncio.ensure_future(self._sink.play(audio.wav))
            await _settle(self._play_op, "sink.play")
            self._play_op = None

    def _finish(self, turn: int) -> None:
        self._started.discard(turn)
        if done := self._done.pop(turn, None):
            done.set()
            self._emit("finished", turn)

    def _emit(self, kind: SpeechEventKind, turn: int) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(SpeechEvent(kind, turn))
        except Exception:
            logger.exception("speech: on_event callback failed")


async def _settle[T](op: Awaitable[T], what: str) -> T | None:
    """Await an operation that ``interrupt()`` may cancel, without cancelling the caller.

    Returns its result, or None if it was cancelled or failed (failures are logged, so a
    bad chunk is skipped and the pipeline carries on). If the *caller* is cancelled
    (``aclose``), the operation is cancelled and awaited too, so no task leaks.
    """
    task = asyncio.ensure_future(op)
    try:
        await asyncio.wait({task})
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    if task.cancelled():
        return None
    if (error := task.exception()) is not None:
        logger.error("speech: %s failed, skipping chunk: %s", what, error)
        return None
    return task.result()
