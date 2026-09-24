"""Local-first providers on one ``SqliteStore``: Jarvis works standalone with these.

Times are stored as fixed-width UTC ISO-8601 text, so string order is time order.
"""

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from jarvis_agent.store.base import (
    JSON,
    Event,
    Note,
    NotFoundError,
    Notification,
    Role,
    Todo,
    Turn,
)
from jarvis_agent.store.sqlite import SqliteStore

Clock = Callable[[], datetime]
ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})

# Explicit column lists (not SELECT *): later migrations may add columns.
NOTE_COLUMNS = "id, title, body, created_at, updated_at"
TODO_COLUMNS = "id, title, done, due, created_at, updated_at"
EVENT_COLUMNS = 'id, title, start, "end", location, notes, created_at, updated_at'
TURN_COLUMNS = "id, role, content, created_at"
NOTIFICATION_COLUMNS = "id, kind, payload, created_at"
COLUMNS = {"notes": NOTE_COLUMNS, "todos": TODO_COLUMNS, "events": EVENT_COLUMNS}


def utc_now() -> datetime:
    return datetime.now(UTC)


class LocalNotes:
    def __init__(self, db: SqliteStore, clock: Clock = utc_now) -> None:
        self._db = db
        self._clock = clock

    async def create(self, title: str, body: str = "") -> Note:
        now = _ts(self._clock())
        note_id = _new_id()

        def work(conn: sqlite3.Connection) -> Note:
            conn.execute(
                "INSERT INTO notes (id, title, body, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (note_id, title, body, now, now),
            )
            return _get_note(conn, note_id)

        return await self._db.run(work)

    async def get(self, note_id: str) -> Note | None:
        return await self._db.run(lambda conn: _maybe(_get_note, conn, note_id))

    async def find(self, *, query: str | None = None, limit: int = 100) -> list[Note]:
        sql = f"SELECT {NOTE_COLUMNS} FROM notes"
        params: list[object] = []
        if query:
            sql += " WHERE title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\'"
            params += [_like(query)] * 2
        sql += " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        return await self._db.run(lambda conn: [_note(r) for r in conn.execute(sql, params)])

    async def update(self, note: Note) -> Note:
        now = _ts(self._clock())

        def work(conn: sqlite3.Connection) -> Note:
            cursor = conn.execute(
                "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                (note.title, note.body, now, note.id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("note", note.id)
            return _get_note(conn, note.id)

        return await self._db.run(work)

    async def delete(self, note_id: str) -> bool:
        return await self._db.run(lambda conn: _delete(conn, "notes", note_id))


class LocalTodos:
    def __init__(self, db: SqliteStore, clock: Clock = utc_now) -> None:
        self._db = db
        self._clock = clock

    async def create(self, title: str, *, due: datetime | None = None) -> Todo:
        now = _ts(self._clock())
        todo_id = _new_id()
        due_ts = _ts_or_none(due)

        def work(conn: sqlite3.Connection) -> Todo:
            conn.execute(
                "INSERT INTO todos (id, title, done, due, created_at, updated_at)"
                " VALUES (?, ?, 0, ?, ?, ?)",
                (todo_id, title, due_ts, now, now),
            )
            return _get_todo(conn, todo_id)

        return await self._db.run(work)

    async def get(self, todo_id: str) -> Todo | None:
        return await self._db.run(lambda conn: _maybe(_get_todo, conn, todo_id))

    async def find(self, *, include_done: bool = False, limit: int = 100) -> list[Todo]:
        sql = (
            f"SELECT {TODO_COLUMNS} FROM todos"
            + ("" if include_done else " WHERE done = 0")
            + " ORDER BY done, due IS NULL, due, created_at, rowid LIMIT ?"
        )
        return await self._db.run(lambda conn: [_todo(r) for r in conn.execute(sql, (limit,))])

    async def update(self, todo: Todo) -> Todo:
        now = _ts(self._clock())
        due_ts = _ts_or_none(todo.due)

        def work(conn: sqlite3.Connection) -> Todo:
            cursor = conn.execute(
                "UPDATE todos SET title = ?, done = ?, due = ?, updated_at = ? WHERE id = ?",
                (todo.title, int(todo.done), due_ts, now, todo.id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("todo", todo.id)
            return _get_todo(conn, todo.id)

        return await self._db.run(work)

    async def delete(self, todo_id: str) -> bool:
        return await self._db.run(lambda conn: _delete(conn, "todos", todo_id))


class LocalCalendar:
    def __init__(self, db: SqliteStore, clock: Clock = utc_now) -> None:
        self._db = db
        self._clock = clock

    async def create(
        self,
        title: str,
        start: datetime,
        end: datetime,
        *,
        location: str | None = None,
        notes: str | None = None,
    ) -> Event:
        start_ts, end_ts = _span(start, end)
        now = _ts(self._clock())
        event_id = _new_id()

        def work(conn: sqlite3.Connection) -> Event:
            conn.execute(
                'INSERT INTO events (id, title, start, "end", location, notes, created_at,'
                " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, title, start_ts, end_ts, location, notes, now, now),
            )
            return _get_event(conn, event_id)

        return await self._db.run(work)

    async def get(self, event_id: str) -> Event | None:
        return await self._db.run(lambda conn: _maybe(_get_event, conn, event_id))

    async def between(self, start: datetime, end: datetime) -> list[Event]:
        start_ts, end_ts = _span(start, end)
        # Overlaps [start, end); a zero-length event counts if it sits inside the range.
        sql = (
            f'SELECT {EVENT_COLUMNS} FROM events WHERE start < ? AND ("end" > ? OR start >= ?)'
            " ORDER BY start, rowid"
        )
        params = (end_ts, start_ts, start_ts)
        return await self._db.run(lambda conn: [_event(r) for r in conn.execute(sql, params)])

    async def update(self, event: Event) -> Event:
        start_ts, end_ts = _span(event.start, event.end)
        now = _ts(self._clock())

        def work(conn: sqlite3.Connection) -> Event:
            cursor = conn.execute(
                'UPDATE events SET title = ?, start = ?, "end" = ?, location = ?, notes = ?,'
                " updated_at = ? WHERE id = ?",
                (event.title, start_ts, end_ts, event.location, event.notes, now, event.id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("event", event.id)
            return _get_event(conn, event.id)

        return await self._db.run(work)

    async def delete(self, event_id: str) -> bool:
        return await self._db.run(lambda conn: _delete(conn, "events", event_id))


class LocalKeyValue:
    def __init__(self, db: SqliteStore, clock: Clock = utc_now) -> None:
        self._db = db
        self._clock = clock

    async def get(self, key: str, default: JSON = None) -> JSON:
        def work(conn: sqlite3.Connection) -> JSON:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            return default if row is None else json.loads(row[0])

        return await self._db.run(work)

    async def set(self, key: str, value: JSON) -> None:
        encoded = json.dumps(value)  # fails fast, before touching the db
        now = _ts(self._clock())
        await self._db.run(
            lambda conn: conn.execute(
                "INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT (key)"
                " DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, encoded, now),
            )
        )

    async def delete(self, key: str) -> bool:
        return await self._db.run(
            lambda conn: conn.execute("DELETE FROM kv WHERE key = ?", (key,)).rowcount > 0
        )

    async def keys(self, prefix: str = "") -> list[str]:
        sql = "SELECT key FROM kv WHERE substr(key, 1, ?) = ? ORDER BY key"
        params = (len(prefix), prefix)
        return await self._db.run(lambda conn: [r[0] for r in conn.execute(sql, params)])


class LocalConversationMemory:
    """Keeps the newest ``keep`` turns (``None`` = unbounded) so the store stays small."""

    def __init__(self, db: SqliteStore, clock: Clock = utc_now, keep: int | None = 1000) -> None:
        self._db = db
        self._clock = clock
        self._keep = keep

    async def append(self, role: Role, content: str) -> Turn:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        now = _ts(self._clock())

        def work(conn: sqlite3.Connection) -> Turn:
            cursor = conn.execute(
                "INSERT INTO turns (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, now),
            )
            if self._keep is not None:
                conn.execute(
                    "DELETE FROM turns WHERE id <= ?", (_int(cursor.lastrowid) - self._keep,)
                )
            row = conn.execute(
                f"SELECT {TURN_COLUMNS} FROM turns WHERE id = ?", (cursor.lastrowid,)
            )
            return _turn(row.fetchone())

        return await self._db.run(work)

    async def recent(self, limit: int = 20) -> list[Turn]:
        def work(conn: sqlite3.Connection) -> list[Turn]:
            rows = conn.execute(
                f"SELECT {TURN_COLUMNS} FROM turns ORDER BY id DESC LIMIT ?", (max(limit, 0),)
            )
            return [_turn(r) for r in reversed(rows.fetchall())]

        return await self._db.run(work)

    async def clear(self) -> None:
        await self._db.run(lambda conn: conn.execute("DELETE FROM turns"))


class LocalNotificationQueue:
    """Acknowledging a notification deletes it."""

    def __init__(self, db: SqliteStore, clock: Clock = utc_now) -> None:
        self._db = db
        self._clock = clock

    async def push(self, kind: str, payload: JSON = None) -> Notification:
        encoded = json.dumps(payload)
        now = _ts(self._clock())

        def work(conn: sqlite3.Connection) -> Notification:
            cursor = conn.execute(
                "INSERT INTO notifications (kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, encoded, now),
            )
            row = conn.execute(
                f"SELECT {NOTIFICATION_COLUMNS} FROM notifications WHERE id = ?",
                (cursor.lastrowid,),
            )
            return _notification(row.fetchone())

        return await self._db.run(work)

    async def pending(self, limit: int = 50) -> list[Notification]:
        sql = f"SELECT {NOTIFICATION_COLUMNS} FROM notifications ORDER BY id LIMIT ?"
        return await self._db.run(
            lambda conn: [_notification(r) for r in conn.execute(sql, (limit,))]
        )

    async def ack(self, notification_id: int) -> bool:
        return await self._db.run(
            lambda conn: (
                conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,)).rowcount
                > 0
            )
        )


# -- helpers ---------------------------------------------------------------------------


def _new_id() -> str:
    return uuid.uuid4().hex


def _ts(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"naive datetime {value!r}: pass a timezone-aware one")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ts_or_none(value: datetime | None) -> str | None:
    return None if value is None else _ts(value)


def _span(start: datetime, end: datetime) -> tuple[str, str]:
    start_ts, end_ts = _ts(start), _ts(end)
    if end_ts < start_ts:
        raise ValueError(f"end {end.isoformat()} is before start {start.isoformat()}")
    return start_ts, end_ts


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _int(value: int | None) -> int:
    assert value is not None  # set by every INSERT
    return value


def _delete(conn: sqlite3.Connection, table: str, record_id: str) -> bool:
    return conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,)).rowcount > 0


def _maybe[T](
    get: Callable[[sqlite3.Connection, str], T], conn: sqlite3.Connection, record_id: str
) -> T | None:
    try:
        return get(conn, record_id)
    except NotFoundError:
        return None


def _one(conn: sqlite3.Connection, table: str, kind: str, record_id: str) -> tuple:
    sql = f"SELECT {COLUMNS[table]} FROM {table} WHERE id = ?"
    row = conn.execute(sql, (record_id,)).fetchone()
    if row is None:
        raise NotFoundError(kind, record_id)
    return row


def _get_note(conn: sqlite3.Connection, note_id: str) -> Note:
    return _note(_one(conn, "notes", "note", note_id))


def _get_todo(conn: sqlite3.Connection, todo_id: str) -> Todo:
    return _todo(_one(conn, "todos", "todo", todo_id))


def _get_event(conn: sqlite3.Connection, event_id: str) -> Event:
    return _event(_one(conn, "events", "event", event_id))


# Row mappers take rows in the *_COLUMNS order above.


def _note(row: tuple) -> Note:
    id_, title, body, created, updated = row
    return Note(id_, title, body, _dt(created), _dt(updated))


def _todo(row: tuple) -> Todo:
    id_, title, done, due, created, updated = row
    return Todo(
        id_, title, bool(done), None if due is None else _dt(due), _dt(created), _dt(updated)
    )


def _event(row: tuple) -> Event:
    id_, title, start, end, location, notes, created, updated = row
    return Event(id_, title, _dt(start), _dt(end), location, notes, _dt(created), _dt(updated))


def _turn(row: tuple) -> Turn:
    id_, role, content, created = row
    return Turn(id_, role, content, _dt(created))


def _notification(row: tuple) -> Notification:
    id_, kind, payload, created = row
    return Notification(id_, kind, json.loads(payload), _dt(created))
