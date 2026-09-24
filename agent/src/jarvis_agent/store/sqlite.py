"""The SQLite database behind the local providers: connection, migrations, snapshot/restore.

One connection per store, guarded by a lock; every call runs in a worker thread via
``asyncio.to_thread`` so disk I/O never blocks the event loop. File databases use WAL mode;
``:memory:`` works too (tests).

Schema changes are forward-only migrations tracked in ``PRAGMA user_version``. Add a new
entry to ``MIGRATIONS``; never edit a released one.

Reader compatibility (#67): each migration declares ``min_reader``, the oldest schema
version that can still read the file after it runs; the database keeps the highest one in
``schema_meta``. An additive migration (new tables, or new columns that are nullable or
have a default; nothing dropped, renamed or retyped) keeps the previous ``min_reader``, so
an older release still opens the file after a rollback. A breaking migration sets
``min_reader`` to its own number. A build opens a file with a newer ``user_version`` only if
its ``SCHEMA_VERSION >= min_reader``, and leaves that file's version as it is.
"""

import asyncio
import contextlib
import os
import sqlite3
import threading
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import NamedTuple

from jarvis_agent.store.base import StoreError

MEMORY = ":memory:"


class Migration(NamedTuple):
    script: str
    min_reader: int  # oldest schema version that can read the file after this migration


MIGRATIONS: tuple[Migration, ...] = (
    # 1: initial schema. Times are UTC ISO-8601 text (fixed width, so they sort as strings).
    Migration(
        min_reader=1,
        script="""
    CREATE TABLE schema_meta (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        min_reader INTEGER NOT NULL
    );
    CREATE TABLE notes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE todos (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        due TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE events (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        start TEXT NOT NULL,
        "end" TEXT NOT NULL,
        location TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK ("end" >= start)
    );
    CREATE INDEX events_start ON events (start);
    CREATE TABLE kv (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    ),
)
SCHEMA_VERSION = len(MIGRATIONS)


class SqliteStore:
    """A migrated SQLite database; the local providers share one instance."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = _connect(self.path)
        try:
            _migrate(self._conn)
        except BaseException:
            self._conn.close()
            raise

    @classmethod
    async def open(cls, path: str | Path) -> SqliteStore:
        return await asyncio.to_thread(cls, path)

    async def run[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``work`` with the connection, in a worker thread, as one transaction."""
        return await asyncio.to_thread(self._run_locked, work)

    async def snapshot(self, dest: str | Path) -> Path:
        """Write a consistent copy of the database to ``dest`` (atomically replaced).

        Uses SQLite's online backup, so it is safe while the store is in use. The copy is
        self-contained (no WAL side files).
        """
        return await asyncio.to_thread(self._with_lock, _snapshot, Path(dest))

    async def restore(self, src: str | Path) -> None:
        """Replace the whole database with the snapshot at ``src``, then migrate it forward.

        A snapshot from a newer schema (a later release) is refused.
        """
        await asyncio.to_thread(self._with_lock, _restore, Path(src))

    async def schema_version(self) -> int:
        return await self.run(_user_version)

    async def aclose(self) -> None:
        await asyncio.to_thread(self._close)

    def _run_locked[T](self, work: Callable[[sqlite3.Connection], T]) -> T:
        def in_transaction(conn: sqlite3.Connection) -> T:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = work(conn)
                conn.execute("COMMIT")  # can fail too (disk full, deferred constraint)
            except BaseException:
                _rollback(conn)
                raise
            return result

        return self._with_lock(in_transaction)

    def _with_lock[T](self, work: Callable[..., T], *args: object) -> T:
        with self._lock:
            if self._conn is None:
                raise StoreError(f"state store {self.path!r} is closed")
            return work(self._conn, *args)

    def _close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def _connect(path: str) -> sqlite3.Connection:
    try:
        if path != MEMORY:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # autocommit=True: transactions are explicit (BEGIN/COMMIT in SqliteStore.run).
        conn = sqlite3.connect(path, autocommit=True, check_same_thread=False)
    except (OSError, sqlite3.Error) as exc:
        raise StoreError(f"cannot open state store {path!r}: {exc}") from exc
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if path != MEMORY:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")  # durable across crashes in WAL mode
    return conn


def _rollback(conn: sqlite3.Connection) -> None:
    """Roll back an open transaction; some errors already did, and a failing rollback must
    not mask the original error."""
    if conn.in_transaction:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _min_reader(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT min_reader FROM schema_meta WHERE id = 1").fetchone()
    except sqlite3.OperationalError:  # no schema_meta table
        return None
    return None if row is None else int(row[0])


def _migrate(conn: sqlite3.Connection, what: str = "state store") -> None:
    """Bring ``conn`` up to ``SCHEMA_VERSION``, or accept a newer file this build can read."""
    version = _user_version(conn)
    if version > SCHEMA_VERSION:
        min_reader = _min_reader(conn)
        if min_reader is None or min_reader > SCHEMA_VERSION:
            needs = "an unknown version" if min_reader is None else f"v{min_reader}"
            raise StoreError(
                f"{what} schema v{version} is newer than this build (v{SCHEMA_VERSION}) and "
                f"needs a reader of at least {needs}; refusing to open it"
            )
    for number, migration in enumerate(MIGRATIONS[version:], start=version + 1):
        # executescript runs the statements verbatim; user_version is transactional.
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{migration.script}\n"
                "INSERT INTO schema_meta (id, min_reader)"
                f" VALUES (1, {migration.min_reader})"
                " ON CONFLICT (id) DO UPDATE"
                " SET min_reader = max(min_reader, excluded.min_reader);\n"
                f"PRAGMA user_version = {number};\nCOMMIT;"
            )
        except sqlite3.Error as exc:
            _rollback(conn)
            raise StoreError(f"{what} migration v{number} failed: {exc}") from exc
    _check_schema(conn, what)


@cache
def _expected_schema() -> dict[str, frozenset[str]]:
    """Tables and columns this build needs: those of a freshly migrated database."""
    conn = sqlite3.connect(MEMORY, autocommit=True)
    try:
        for migration in MIGRATIONS:
            conn.executescript(migration.script)
        return _schema(conn)
    finally:
        conn.close()


def _schema(conn: sqlite3.Connection) -> dict[str, frozenset[str]]:
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {
        name: frozenset(row[1] for row in conn.execute(f'PRAGMA table_info("{name}")'))
        for (name,) in tables
    }


def _check_schema(conn: sqlite3.Connection, what: str) -> None:
    """Refuse a database missing tables or columns this build uses (extra ones are fine)."""
    actual = _schema(conn)
    missing = sorted(
        table if table not in actual else f"{table}.{column}"
        for table, columns in _expected_schema().items()
        for column in (columns - actual[table] if table in actual else [""])
    )
    if missing:
        raise StoreError(f"{what} is missing {', '.join(missing)}; refusing to open it")


def _snapshot(conn: sqlite3.Connection, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.unlink(missing_ok=True)
    target = sqlite3.connect(tmp)
    try:
        conn.backup(target)
    finally:
        target.close()
    os.replace(tmp, dest)
    return dest


def _restore(conn: sqlite3.Connection, src: Path) -> None:
    if not src.is_file():
        raise StoreError(f"snapshot {str(src)!r} does not exist")
    source = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    try:
        version = _user_version(source)
        if version > SCHEMA_VERSION:
            raise StoreError(
                f"snapshot schema v{version} is newer than this build supports "
                f"(v{SCHEMA_VERSION}); refusing to restore it"
            )
        source.backup(conn)
    except sqlite3.DatabaseError as exc:
        raise StoreError(f"cannot restore snapshot {str(src)!r}: {exc}") from exc
    finally:
        source.close()
    _migrate(conn)
