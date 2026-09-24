"""Speech output queue: segmentation, pipelining, barge-in, errors and lifecycle.

Fakes are gated by events instead of sleeps, so every test is deterministic.
"""

import asyncio
from collections.abc import Callable

import pytest

from jarvis_agent.backends.base import BackendError
from jarvis_agent.backends.mock import MockTTS
from jarvis_agent.speech import NullSink, Segmenter, SpeechEvent, SpeechQueue

pytestmark = pytest.mark.anyio


class FakeTTS:
    """Returns the text as bytes. ``gated`` texts wait for ``release(text)``; ``failing``
    texts raise BackendError."""

    def __init__(self, gated: set[str] | None = None, failing: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.cancelled: list[str] = []
        self.gated = gated or set()
        self.failing = failing or set()
        self._gates: dict[str, asyncio.Event] = {}

    def release(self, text: str) -> None:
        self._gates.setdefault(text, asyncio.Event()).set()

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        if text in self.failing:
            raise BackendError("tts", f"cannot say {text!r}")
        if text in self.gated:
            try:
                await self._gates.setdefault(text, asyncio.Event()).wait()
            except asyncio.CancelledError:
                self.cancelled.append(text)
                raise
        return text.encode()


class FakeSink:
    """Records playback. With ``hold=True`` each play waits until ``finish()`` or ``stop()``."""

    def __init__(self, hold: bool = False, fail: set[bytes] | None = None) -> None:
        self.hold = hold
        self.fail = fail or set()
        self.started: list[bytes] = []
        self.played: list[bytes] = []
        self.stops = 0
        self._current: asyncio.Event | None = None

    @property
    def playing(self) -> bool:
        return self._current is not None

    def finish(self) -> None:
        assert self._current is not None, "nothing is playing"
        self._current.set()
        self._current = None

    async def play(self, wav: bytes) -> None:
        self.started.append(wav)
        if wav in self.fail:
            raise BackendError("sink", "device busy")
        if self.hold:
            done = self._current = asyncio.Event()
            try:
                await done.wait()
            finally:
                if self._current is done:
                    self._current = None
        self.played.append(wav)

    async def stop(self) -> None:
        self.stops += 1
        if self._current is not None:
            self.finish()


async def until(predicate: Callable[[], bool], steps: int = 200) -> None:
    """Yield to the event loop until ``predicate`` holds (no wall-clock sleeps)."""
    for _ in range(steps):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition never became true")


# ---- segmentation ----------------------------------------------------------------------


def test_segmenter_splits_sentences_from_deltas() -> None:
    seg = Segmenter()
    assert seg.push("Hello there. How ") == ["Hello there."]
    assert seg.push("are you? Pi is 3.") == ["How are you?"]
    assert seg.push("14 today") == []
    assert seg.flush() == ["Pi is 3.14 today"]
    assert seg.flush() == []


def test_segmenter_cuts_long_sentences_at_clauses_and_hard_limit() -> None:
    seg = Segmenter(min_clause_chars=10, max_chars=30)
    assert seg.push("Short, then a longer clause, and more") == ["Short, then a longer clause,"]
    assert seg.flush() == ["and more"]
    words = "word " * 10
    long_seg = Segmenter(min_clause_chars=10, max_chars=30)
    chunks = long_seg.push(words)
    assert len(chunks) == 1
    chunks += long_seg.flush()
    assert all(len(c) <= 30 for c in chunks) and " ".join(chunks) == words.strip()


def test_segmenter_hard_cut_wins_over_a_later_boundary() -> None:
    # One 250-char sentence: its "." lies past max_chars, so the hard cut must still apply.
    sentence = ("word " * 50).strip() + ". "
    seg = Segmenter()
    chunks = seg.push(sentence) + seg.flush()
    assert len(chunks) == 2
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks) == sentence.strip()


def test_segmenter_drops_unspeakable_and_handles_newlines() -> None:
    seg = Segmenter()
    assert seg.push("... \nFirst line\nSecond!") == ["First line"]
    assert seg.flush() == ["Second!"]


# ---- ordering & events -----------------------------------------------------------------


async def test_turns_play_in_order_with_events() -> None:
    events: list[SpeechEvent] = []
    tts, sink = FakeTTS(), FakeSink()
    async with SpeechQueue(tts, sink, on_event=events.append) as speech:
        first = speech.begin_turn()
        for delta in ["One. ", "Two", ". Three"]:
            speech.feed(first, delta)
        second = speech.say("Four. Five.")  # ends `first` implicitly, then queues
        speech.end_turn(first)  # already ended: no-op
        await speech.wait(second)
        assert not speech.speaking

    assert sink.played == [b"One.", b"Two.", b"Three", b"Four.", b"Five."]
    assert events == [
        SpeechEvent("started", first),
        SpeechEvent("finished", first),
        SpeechEvent("started", second),
        SpeechEvent("finished", second),
    ]


async def test_works_with_mock_backends() -> None:
    async with SpeechQueue(MockTTS(), NullSink()) as speech:
        await speech.wait(speech.say("Hello. World."))
        assert not speech.speaking


# ---- pipelining & non-blocking ---------------------------------------------------------


async def test_next_chunk_is_synthesized_while_current_plays() -> None:
    tts, sink = FakeTTS(), FakeSink(hold=True)
    async with SpeechQueue(tts, sink, lookahead=1) as speech:
        turn = speech.say("A. B. C. D.")
        await until(lambda: sink.playing)
        # "A." plays; "B." is synthesized and waiting, "C." synthesized too (lookahead
        # buffer full, so synthesis of "D." has not started).
        await until(lambda: tts.calls == ["A.", "B.", "C."])
        for _ in range(20):
            await asyncio.sleep(0)
        assert tts.calls == ["A.", "B.", "C."]
        assert sink.started == [b"A."]
        for _ in range(4):
            await until(lambda: sink.playing)
            sink.finish()
        await speech.wait(turn)
    assert sink.played == [b"A.", b"B.", b"C.", b"D."]


async def test_enqueue_never_blocks_and_drops_on_overflow() -> None:
    tts = FakeTTS(gated={"Stuck."})
    async with SpeechQueue(tts, NullSink(), max_pending=2) as speech:
        speech.say("Stuck.")
        await until(lambda: tts.calls == ["Stuck."])  # synthesis hangs from here on
        # These are plain synchronous calls: they return even though TTS is stuck.
        turn = speech.say("One. Two. Three. Four.")
        assert speech.dropped == 2
        tts.release("Stuck.")
        await speech.wait(turn)
    assert tts.calls == ["Stuck.", "One.", "Two."]


async def test_turns_are_bounded_when_synthesis_is_stuck() -> None:
    events: list[SpeechEvent] = []
    tts = FakeTTS(gated={"Stuck."})
    async with SpeechQueue(
        tts, NullSink(), on_event=events.append, max_pending=2, max_turns=3
    ) as speech:
        speech.say("Stuck.")
        await until(lambda: tts.calls == ["Stuck."])  # synthesis hangs from here on
        # Empty / punctuation-only replies enqueue only an end marker; they must not pile up.
        turns = [speech.say(text) for _ in range(300) for text in ("", "...", "Hi.")]
        assert len(speech._pending) <= 2 + 3
        assert len(speech._done) <= 3
        assert speech.dropped_turns == len(turns) - 2  # "Stuck." + 2 more fit in 3 turns
        tts.release("Stuck.")
        await asyncio.gather(*(speech.wait(turn) for turn in turns))
        assert not speech.speaking

    ends = [e.turn for e in events if e.kind in ("finished", "interrupted")]
    assert sorted(ends) == list(range(1, len(turns) + 2))  # every turn ended exactly once


# ---- barge-in --------------------------------------------------------------------------


async def test_interrupt_stops_playback_and_drops_stale_chunks() -> None:
    events: list[SpeechEvent] = []
    tts, sink = FakeTTS(gated={"C."}), FakeSink(hold=True)
    async with SpeechQueue(tts, sink, on_event=events.append) as speech:
        old = speech.begin_turn()
        speech.feed(old, "A. B. C. D. E.")
        await until(lambda: sink.playing and "C." in tts.calls)  # C in flight, B ready

        await speech.interrupt()
        assert sink.stops == 1
        assert not speech.speaking
        await until(lambda: tts.cancelled == ["C."])  # in-flight synthesis was cancelled

        speech.feed(old, "Late delta. ")  # stale producer: ignored
        speech.end_turn(old)
        new = speech.say("Fresh.")
        await until(lambda: sink.playing)
        sink.finish()
        await speech.wait(new)

    assert sink.started == [b"A.", b"Fresh."]
    assert "D." not in tts.calls and "Late delta." not in tts.calls
    assert events == [
        SpeechEvent("started", old),
        SpeechEvent("interrupted", old),
        SpeechEvent("started", new),
        SpeechEvent("finished", new),
    ]


async def test_interrupt_drops_queued_turns_too() -> None:
    events: list[SpeechEvent] = []
    sink = FakeSink(hold=True)
    async with SpeechQueue(FakeTTS(), sink, on_event=events.append) as speech:
        first = speech.say("First.")
        second = speech.say("Second.")
        await until(lambda: sink.playing)
        await speech.interrupt()
        await speech.wait(second)  # returns: interrupted counts as done
        for _ in range(20):
            await asyncio.sleep(0)
    assert sink.started == [b"First."]
    assert SpeechEvent("interrupted", first) in events
    assert SpeechEvent("interrupted", second) in events


# ---- errors ----------------------------------------------------------------------------


async def test_tts_and_sink_errors_skip_the_chunk_and_continue() -> None:
    events: list[SpeechEvent] = []

    def flaky_listener(event: SpeechEvent) -> None:
        events.append(event)
        raise RuntimeError("listener bug")  # must not kill the pipeline either

    tts, sink = FakeTTS(failing={"Bad."}), FakeSink(fail={b"Worse."})
    async with SpeechQueue(tts, sink, on_event=flaky_listener) as speech:
        turn = speech.say("Good. Bad. Worse. Fine.")
        await speech.wait(turn)
    assert sink.played == [b"Good.", b"Fine."]
    assert [e.kind for e in events] == ["started", "finished"]


# ---- lifecycle -------------------------------------------------------------------------


async def test_aclose_cancels_everything_without_leaking_tasks() -> None:
    before = asyncio.all_tasks()
    tts, sink = FakeTTS(gated={"B."}), FakeSink(hold=True)
    speech = SpeechQueue(tts, sink)
    speech.start()
    with pytest.raises(RuntimeError):
        speech.start()
    speech.say("A. B.")
    await until(lambda: sink.playing and "B." in tts.calls)

    await speech.aclose()
    await speech.aclose()  # idempotent
    assert sink.stops == 1
    assert tts.cancelled == ["B."]
    assert asyncio.all_tasks() == before


async def test_aclose_ends_turns_accepted_before_start() -> None:
    events: list[SpeechEvent] = []
    speech = SpeechQueue(FakeTTS(), FakeSink(), on_event=events.append)
    turn = speech.say("Queued but never started.")
    assert speech.speaking

    await speech.aclose()
    assert not speech.speaking
    await asyncio.wait_for(speech.wait(turn), timeout=1)
    assert [e.kind for e in events] == ["interrupted"]


def test_rejects_bad_sizes() -> None:
    with pytest.raises(ValueError):
        SpeechQueue(MockTTS(), NullSink(), lookahead=0)
    with pytest.raises(ValueError):
        SpeechQueue(MockTTS(), NullSink(), max_turns=0)
    with pytest.raises(ValueError):
        Segmenter(min_clause_chars=50, max_chars=10)
