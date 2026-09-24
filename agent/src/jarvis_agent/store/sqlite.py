"""The SQLite database behind the local providers: connection, migrations, snapshot/restore.

One connection per store, guarded by a lock; every call runs in a worker thread via
``asyncio.to_thread`` so disk I/O never blocks the event loop. File databases use WAL mode;
``:memory:`` works too (tests).

Schema changes are forward-only migrations tracked in ``PRAGMA user_version``. Add a new
entry to ``MIGRATIONS``; never edit a released one. Per #67, a migration must stay readable
by the previous release (add tables/columns, don't drop or rename), so a rollback that
restores a snapshot never meets a schema it can't read.
"""

import asyncio
import contextlib
import os
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from jarvis_agent.store.base import StoreError

MEMORY = ":memory:"

MIGRATIONS: tuple[str, ...] = (
    # 1: initial schema. Times are UTC ISO-8601 text (fixed width, so they sort as strings).
    """
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


def _migrate(conn: sqlite3.Connection) -> None:
    version = _user_version(conn)
    if version > SCHEMA_VERSION:
        raise StoreError(
            f"state store schema v{version} is newer than this build supports "
            f"(v{SCHEMA_VERSION}); refusing to open it"
        )
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        # executescript runs the statements verbatim; user_version is transactional.
        try:
            conn.executescript(
                f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;"
            )
        except sqlite3.Error as exc:
            _rollback(conn)
            raise StoreError(f"state store migration v{number} failed: {exc}") from exc


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
