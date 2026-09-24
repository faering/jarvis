"""Local state store: providers, migrations, snapshot/restore, config and concurrency."""

import asyncio
import dataclasses
import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis_agent.store import (
    SCHEMA_VERSION,
    FaelabProviders,
    NotFoundError,
    SqliteStore,
    State,
    StoreConfigError,
    StoreError,
    StoreSettings,
    open_state,
)
from jarvis_agent.store.local import LocalConversationMemory, LocalNotes

T0 = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


class StepClock:
    """Deterministic clock: every reading is one second after the previous one."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture(params=["file", "memory"])
async def state(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[State]:
    db = str(tmp_path / "jarvis.db") if request.param == "file" else ":memory:"
    opened = await open_state(StoreSettings(db=db), clock=StepClock())
    yield opened
    await opened.aclose()


# -- providers -------------------------------------------------------------------------


@pytest.mark.anyio
async def test_note_search_folds_unicode_case(state: State) -> None:
    accented = await state.notes.create("Éclair recipe", "STRASSE")
    await state.notes.create("Groceries", "milk")
    assert [n.id for n in await state.notes.find(query="éclair")] == [accented.id]
    assert [n.id for n in await state.notes.find(query="straße")] == [accented.id]


@pytest.mark.anyio
async def test_notes_crud_and_search(state: State) -> None:
    first = await state.notes.create("Groceries", "milk, eggs")
    second = await state.notes.create("Printer", "calibrate 100% flow")

    assert await state.notes.get(first.id) == first
    assert await state.notes.get("missing") is None
    assert [n.id for n in await state.notes.find()] == [second.id, first.id]
    assert [n.id for n in await state.notes.find(query="EGGS")] == [first.id]
    assert [n.id for n in await state.notes.find(query="100%")] == [second.id]
    assert await state.notes.find(query="_") == []  # no wildcards: matched literally
    assert await state.notes.find(limit=1) == [second]

    edited = await state.notes.update(dataclasses.replace(first, body="milk"))
    assert (edited.body, edited.created_at) == ("milk", first.created_at)
    assert edited.updated_at > first.updated_at
    assert (await state.notes.find())[0].id == first.id  # most recently updated first

    assert await state.notes.delete(first.id) is True
    assert await state.notes.delete(first.id) is False
    with pytest.raises(NotFoundError):
        await state.notes.update(first)


@pytest.mark.anyio
async def test_todos_crud_and_ordering(state: State) -> None:
    undated = await state.todo.create("someday")
    later = await state.todo.create("later", due=T0 + timedelta(days=2))
    sooner = await state.todo.create("sooner", due=T0 + timedelta(days=1))
    assert undated.done is False and undated.due is None
    assert sooner.due == T0 + timedelta(days=1)

    assert [t.title for t in await state.todo.find()] == ["sooner", "later", "someday"]

    done = await state.todo.update(dataclasses.replace(sooner, done=True))
    assert done.done is True
    assert [t.title for t in await state.todo.find()] == ["later", "someday"]
    assert [t.title for t in await state.todo.find(include_done=True)] == [
        "later",
        "someday",
        "sooner",
    ]

    cleared = await state.todo.update(dataclasses.replace(later, due=None))
    assert cleared.due is None
    assert await state.todo.delete(undated.id) is True
    assert await state.todo.get(undated.id) is None
    with pytest.raises(NotFoundError):
        await state.todo.update(undated)


@pytest.mark.anyio
async def test_calendar_crud_and_range_queries(state: State) -> None:
    hour = timedelta(hours=1)
    standup = await state.calendar.create("standup", T0, T0 + hour / 4, location="office")
    lunch = await state.calendar.create("lunch", T0 + 3 * hour, T0 + 4 * hour)
    # Another timezone: stored and compared in UTC, returned as UTC.
    cet = timezone(timedelta(hours=2))
    call = await state.calendar.create("call", T0 + 2 * hour, T0 + 3 * hour, notes="dial in")
    reminder = await state.calendar.create("ping", T0 + 5 * hour, T0 + 5 * hour)  # zero-length
    assert call.start == (T0 + 2 * hour).astimezone(cet)
    assert standup.location == "office" and call.notes == "dial in"

    async def titles(start: datetime, end: datetime) -> list[str]:
        return [e.title for e in await state.calendar.between(start, end)]

    assert await titles(T0, T0 + 24 * hour) == ["standup", "call", "lunch", "ping"]
    assert await titles(T0 + hour / 8, T0 + hour) == ["standup"]  # overlaps partially
    assert await titles(T0 + 3 * hour, T0 + 3 * hour + 1 * hour) == ["lunch"]  # [start, end)
    assert await titles(T0 + 4 * hour, T0 + 5 * hour) == []  # lunch ended, ping not yet
    assert await titles(T0 + 5 * hour, T0 + 6 * hour) == ["ping"]
    # An empty range [t, t) matches nothing, even events spanning t or sitting at t.
    assert await titles(T0 + hour / 8, T0 + hour / 8) == []
    assert await titles(T0 + 5 * hour, T0 + 5 * hour) == []
    assert await titles((T0 + 2 * hour).astimezone(cet), (T0 + 3 * hour).astimezone(cet)) == [
        "call"
    ]

    moved = await state.calendar.update(
        dataclasses.replace(lunch, start=T0 + 6 * hour, end=T0 + 7 * hour)
    )
    assert moved.start == T0 + 6 * hour
    assert await titles(T0 + 3 * hour, T0 + 4 * hour) == []

    assert await state.calendar.delete(standup.id) is True
    assert await state.calendar.get(standup.id) is None
    assert await state.calendar.get(reminder.id) == reminder


@pytest.mark.anyio
async def test_calendar_rejects_bad_times(state: State) -> None:
    with pytest.raises(ValueError, match="before start"):
        await state.calendar.create("backwards", T0, T0 - timedelta(minutes=1))
    with pytest.raises(ValueError, match="naive"):
        await state.calendar.create("naive", datetime(2026, 1, 1), datetime(2026, 1, 2))
    with pytest.raises(ValueError, match="before start"):
        await state.calendar.between(T0, T0 - timedelta(days=1))


@pytest.mark.anyio
async def test_key_value(state: State) -> None:
    assert await state.kv.get("prefs.voice") is None
    assert await state.kv.get("prefs.voice", "amy") == "amy"

    await state.kv.set("prefs.voice", "jarvis")
    await state.kv.set("prefs.units", {"temp": "C", "metric": True})
    await state.kv.set("cache.weather", [1, 2.5, None])
    await state.kv.set("prefs.voice", "friday")  # overwrite

    assert await state.kv.get("prefs.voice") == "friday"
    assert await state.kv.get("prefs.units") == {"temp": "C", "metric": True}
    assert await state.kv.keys("prefs.") == ["prefs.units", "prefs.voice"]
    assert await state.kv.keys() == ["cache.weather", "prefs.units", "prefs.voice"]
    assert await state.kv.keys("%") == []

    assert await state.kv.delete("cache.weather") is True
    assert await state.kv.delete("cache.weather") is False
    with pytest.raises(TypeError):
        await state.kv.set("bad", object())


@pytest.mark.anyio
async def test_conversation_memory_order_and_limit(state: State) -> None:
    for index in range(5):
        await state.memory.append("user" if index % 2 == 0 else "assistant", f"turn {index}")

    recent = await state.memory.recent(3)
    assert [t.content for t in recent] == ["turn 2", "turn 3", "turn 4"]  # oldest first
    assert [t.role for t in recent] == ["user", "assistant", "user"]
    assert [t.id for t in recent] == sorted(t.id for t in recent)
    assert len(await state.memory.recent(100)) == 5
    assert await state.memory.recent(0) == []

    with pytest.raises(ValueError, match="role"):
        await state.memory.append("robot", "beep")  # type: ignore[arg-type]

    await state.memory.clear()
    assert await state.memory.recent() == []


@pytest.mark.anyio
async def test_conversation_memory_keeps_only_newest_turns(tmp_path: Path) -> None:
    db = await SqliteStore.open(tmp_path / "jarvis.db")
    memory = LocalConversationMemory(db, keep=3)
    for index in range(10):
        await memory.append("user", str(index))
    assert [t.content for t in await memory.recent(100)] == ["7", "8", "9"]
    await db.aclose()


@pytest.mark.anyio
async def test_notification_queue(state: State) -> None:
    first = await state.notifications.push("print.done", {"job": "benchy"})
    second = await state.notifications.push("reminder")
    assert first.payload == {"job": "benchy"} and second.payload is None

    assert [n.id for n in await state.notifications.pending()] == [first.id, second.id]
    assert await state.notifications.ack(first.id) is True
    assert await state.notifications.ack(first.id) is False
    assert await state.notifications.pending() == [second]


# -- database: migrations, snapshot/restore, lifecycle ---------------------------------


@pytest.mark.anyio
async def test_migrates_empty_db_and_reopens_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "jarvis.db"  # parent dirs are created
    first = await open_state(StoreSettings(db=str(path)))
    assert await first.db.schema_version() == SCHEMA_VERSION
    note = await first.notes.create("persisted")
    await first.aclose()

    second = await open_state(StoreSettings(db=str(path)))
    assert await second.db.schema_version() == SCHEMA_VERSION
    assert await second.notes.get(note.id) == note
    await second.aclose()

    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()


@pytest.mark.anyio
async def test_refuses_a_db_from_a_newer_schema(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(StoreError, match="newer"):
        await SqliteStore.open(path)


def make_future(path: Path, *, min_reader: int | None = None) -> None:
    """Simulate a later release's migration on an existing store file (additive by default)."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE future_things (id INTEGER PRIMARY KEY)")
    conn.execute("ALTER TABLE notes ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    if min_reader is not None:
        conn.execute("UPDATE schema_meta SET min_reader = ?", (min_reader,))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()


@pytest.mark.anyio
async def test_older_build_reads_a_newer_additive_db(tmp_path: Path) -> None:
    path = tmp_path / "jarvis.db"
    state = await open_state(StoreSettings(db=str(path)))
    note = await state.notes.create("from before the upgrade")
    await state.aclose()
    make_future(path)  # the next release added a table and a defaulted column

    state = await open_state(StoreSettings(db=str(path)))  # e.g. after a rollback
    assert await state.notes.get(note.id) == note
    assert (await state.notes.create("written by the older build")).title
    assert await state.db.schema_version() == SCHEMA_VERSION + 1  # never downgraded
    await state.aclose()


@pytest.mark.anyio
async def test_refuses_a_newer_db_that_needs_a_newer_reader(tmp_path: Path) -> None:
    path = tmp_path / "jarvis.db"
    await (await SqliteStore.open(path)).aclose()
    make_future(path, min_reader=SCHEMA_VERSION + 1)  # a breaking migration
    with pytest.raises(StoreError, match=f"at least v{SCHEMA_VERSION + 1}"):
        await SqliteStore.open(path)


@pytest.mark.anyio
async def test_refuses_a_db_missing_tables(tmp_path: Path) -> None:
    path = tmp_path / "jarvis.db"
    await (await SqliteStore.open(path)).aclose()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE todos")
    conn.close()
    with pytest.raises(StoreError, match="missing todos"):
        await SqliteStore.open(path)


@pytest.mark.anyio
async def test_snapshot_refuses_the_live_database(tmp_path: Path) -> None:
    path = tmp_path / "jarvis.db"
    state = await open_state(StoreSettings(db=str(path)))
    try:
        await state.kv.set("k", "v")
        with pytest.raises(StoreError, match="live database"):
            await state.snapshot(path)
        with pytest.raises(StoreError, match="live database"):
            await state.snapshot(tmp_path / "." / "jarvis.db")
        assert await state.kv.get("k") == "v"  # still writing to the real file
    finally:
        await state.aclose()


@pytest.mark.anyio
async def test_snapshot_restore_round_trip(state: State, tmp_path: Path) -> None:
    note = await state.notes.create("before promote")
    await state.kv.set("prefs.voice", "jarvis")
    await state.memory.append("user", "hello")

    snapshot = await state.snapshot(tmp_path / "snapshots" / "pre-promote.db")
    assert snapshot.is_file()
    assert snapshot.stat().st_size < 256 * 1024  # a near-empty store is tiny

    await state.notes.delete(note.id)
    await state.notes.create("after promote")
    await state.kv.set("prefs.voice", "friday")
    await state.memory.clear()

    await state.restore(snapshot)
    assert [n.title for n in await state.notes.find()] == ["before promote"]
    assert await state.kv.get("prefs.voice") == "jarvis"
    assert [t.content for t in await state.memory.recent()] == ["hello"]
    assert await state.db.schema_version() == SCHEMA_VERSION

    # Snapshots are overwritten atomically and the store stays usable after a restore.
    await state.snapshot(snapshot)
    assert (await state.notes.create("still writable")).title == "still writable"


@pytest.mark.anyio
async def test_restore_rejects_missing_or_newer_snapshots(state: State, tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="does not exist"):
        await state.restore(tmp_path / "nope.db")

    future = tmp_path / "future.db"
    conn = sqlite3.connect(future)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    await state.kv.set("kept", True)
    with pytest.raises(StoreError, match="newer"):
        await state.restore(future)
    assert await state.kv.get("kept") is True  # untouched


async def assert_restore_refused(state: State, snapshot: Path, match: str) -> None:
    await state.kv.set("live", "kept")
    with pytest.raises(StoreError, match=match):
        await state.restore(snapshot)
    assert await state.kv.get("live") == "kept"  # live database untouched and usable
    await state.kv.set("live", "still writable")
    assert await state.db.schema_version() == SCHEMA_VERSION


@pytest.mark.anyio
async def test_restore_rejects_empty_or_schemaless_files(state: State, tmp_path: Path) -> None:
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    await assert_restore_refused(state, empty, "not a Jarvis state snapshot")
    bare = tmp_path / "bare.db"
    conn = sqlite3.connect(bare)
    conn.execute("CREATE TABLE unrelated (x)")
    conn.close()
    await assert_restore_refused(state, bare, "not a Jarvis state snapshot")


@pytest.mark.anyio
async def test_restore_rejects_corrupt_snapshots(state: State, tmp_path: Path) -> None:
    for index in range(200):
        await state.notes.create(f"note {index}", "x" * 200)  # spans many pages
    snapshot = await state.snapshot(tmp_path / "good.db")
    data = bytearray(snapshot.read_bytes())
    page = 4096
    data[3 * page : 6 * page] = b"\xff" * (3 * page)  # trash some b-tree pages
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(bytes(data))
    await assert_restore_refused(state, corrupt, "corrupt|malformed")

    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"not a sqlite database at all" * 100)
    await assert_restore_refused(state, garbage, "cannot restore")


@pytest.mark.anyio
async def test_restore_rejects_snapshots_missing_tables(state: State, tmp_path: Path) -> None:
    # Claims the current schema version but lacks most tables: migrating would be a no-op.
    partial = tmp_path / "partial.db"
    conn = sqlite3.connect(partial)
    conn.execute("CREATE TABLE notes (id TEXT PRIMARY KEY)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.close()
    await assert_restore_refused(state, partial, "missing")


@pytest.mark.anyio
async def test_restore_reader_compatibility(state: State, tmp_path: Path) -> None:
    note = await state.notes.create("in the snapshot")
    snapshot = await state.snapshot(tmp_path / "newer.db")
    make_future(snapshot)  # taken by a later release with an additive migration
    await state.notes.delete(note.id)
    await state.restore(snapshot)
    assert await state.notes.get(note.id) == note
    assert await state.db.schema_version() == SCHEMA_VERSION + 1

    breaking = await state.snapshot(tmp_path / "breaking.db")
    conn = sqlite3.connect(breaking)
    conn.execute("UPDATE schema_meta SET min_reader = ?", (SCHEMA_VERSION + 2,))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 2}")
    conn.commit()
    conn.close()
    await state.kv.set("live", "kept")
    with pytest.raises(StoreError, match="newer"):
        await state.restore(breaking)
    assert await state.kv.get("live") == "kept"


@pytest.mark.anyio
async def test_closed_store_raises(tmp_path: Path) -> None:
    state = await open_state(StoreSettings(db=":memory:"))
    await state.aclose()
    await state.aclose()  # idempotent
    with pytest.raises(StoreError, match="closed"):
        await state.notes.find()


@pytest.mark.anyio
async def test_failed_work_rolls_back(tmp_path: Path) -> None:
    db = await SqliteStore.open(":memory:")

    def half_done(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO kv (key, value, updated_at) VALUES ('k', '1', 'now')")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await db.run(half_done)
    assert await db.run(lambda conn: conn.execute("SELECT count(*) FROM kv").fetchone()[0]) == 0
    await db.aclose()


@pytest.mark.anyio
async def test_failed_commit_rolls_back() -> None:
    db = await SqliteStore.open(":memory:")

    def fails_at_commit(conn: sqlite3.Connection) -> None:
        # A deferred foreign key is checked only at COMMIT, so the work itself succeeds and
        # the COMMIT raises, leaving the transaction open unless it is rolled back.
        conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE child (parent_id INTEGER"
            " REFERENCES parent (id) DEFERRABLE INITIALLY DEFERRED)"
        )
        conn.execute("INSERT INTO kv (key, value, updated_at) VALUES ('k', '1', 'now')")
        conn.execute("INSERT INTO child VALUES (42)")

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        await db.run(fails_at_commit)

    def check(conn: sqlite3.Connection) -> tuple[int, int]:
        tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE name = 'child'")
        return tables.fetchone()[0], conn.execute("SELECT count(*) FROM kv").fetchone()[0]

    assert await db.run(check) == (0, 0)  # rolled back, and the store is usable again
    await db.aclose()


@pytest.mark.anyio
async def test_many_concurrent_calls(state: State) -> None:
    notes = await asyncio.gather(*(state.notes.create(f"note {i}") for i in range(100)))
    await asyncio.gather(
        *(state.kv.set(f"k{i}", i) for i in range(100)),
        *(state.memory.append("user", str(i)) for i in range(100)),
        *(state.notes.get(n.id) for n in notes),
    )
    assert len(await state.notes.find(limit=1000)) == 100
    assert len(await state.kv.keys("k")) == 100
    assert len(await state.memory.recent(1000)) == 100
    assert len({n.id for n in notes}) == 100


# -- config and provider selection -----------------------------------------------------


def test_env_defaults_to_local() -> None:
    settings = StoreSettings.from_env({})
    assert settings == StoreSettings()
    assert (settings.db, settings.notes, settings.todo, settings.calendar) == (
        "/data/jarvis.db",
        "local",
        "local",
        "local",
    )


def test_env_reads_db_and_providers() -> None:
    settings = StoreSettings.from_env(
        {
            "JARVIS_STATE_DB": " /tmp/x.db ",
            "JARVIS_NOTES_PROVIDER": "Faelab",
            "JARVIS_TODO_PROVIDER": "",
            "JARVIS_CALENDAR_PROVIDER": "local",
        }
    )
    assert (settings.db, settings.notes, settings.todo, settings.calendar) == (
        "/tmp/x.db",
        "faelab",
        "local",
        "local",
    )


def test_env_rejects_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        StoreSettings.from_env({"JARVIS_TODO_PROVIDER": "google"})


@pytest.mark.anyio
async def test_faelab_without_a_provider_is_a_config_error() -> None:
    with pytest.raises(StoreConfigError, match="JARVIS_CALENDAR_PROVIDER=faelab"):
        await open_state(StoreSettings(db=":memory:", calendar="faelab"))


@pytest.mark.anyio
async def test_faelab_provider_overrides_one_domain(tmp_path: Path) -> None:
    # Any object satisfying NotesProvider can stand in for Faelab; here, a second local db.
    remote_db = await SqliteStore.open(":memory:")
    remote_notes = LocalNotes(remote_db)
    state = await open_state(
        StoreSettings(db=str(tmp_path / "jarvis.db"), notes="faelab"),
        faelab=FaelabProviders(notes=remote_notes),
    )
    assert state.notes is remote_notes
    await state.notes.create("lives in faelab")
    await state.todo.create("lives locally")

    local_notes = LocalNotes(state.db)
    assert await local_notes.find() == []  # nothing duplicated locally
    assert [t.title for t in await state.todo.find()] == ["lives locally"]
    await state.aclose()
    await remote_db.aclose()


class EmptyNotes(LocalNotes):
    """A valid provider that is falsey (e.g. a remote collection with ``__len__`` == 0)."""

    def __len__(self) -> int:
        return 0


@pytest.mark.anyio
async def test_falsey_faelab_provider_is_still_used() -> None:
    remote_db = await SqliteStore.open(":memory:")
    remote_notes = EmptyNotes(remote_db)
    assert not remote_notes
    state = await open_state(
        StoreSettings(db=":memory:", notes="faelab"), faelab=FaelabProviders(notes=remote_notes)
    )
    assert state.notes is remote_notes
    await state.aclose()
    await remote_db.aclose()


@pytest.mark.anyio
async def test_unused_faelab_providers_are_ignored() -> None:
    remote_db = await SqliteStore.open(":memory:")
    state = await open_state(
        StoreSettings(db=":memory:"), faelab=FaelabProviders(notes=LocalNotes(remote_db))
    )
    assert isinstance(state.notes, LocalNotes)
    await state.aclose()
    await remote_db.aclose()
