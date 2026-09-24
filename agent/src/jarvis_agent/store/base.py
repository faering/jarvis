"""State interfaces: what the agent needs from a store, independent of who holds the data.

Each domain is a ``typing.Protocol`` with async methods, so the local SQLite providers and
later remote (Faelab) ones are interchangeable. Timestamps are timezone-aware datetimes;
naive ones are rejected.

To change a record, read it, ``dataclasses.replace`` the fields and pass it to ``update``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

JSON = Any  # anything ``json.dumps`` accepts
Role = Literal["system", "user", "assistant"]


class StoreError(Exception):
    """The store failed: closed, unreadable, or a snapshot from a newer schema."""


class NotFoundError(StoreError):
    """``update`` on a record that does not exist."""

    def __init__(self, kind: str, record_id: str) -> None:
        super().__init__(f"{kind} {record_id!r} not found")
        self.kind = kind
        self.record_id = record_id


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Todo:
    id: str
    title: str
    done: bool
    due: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Event:
    """A calendar event over ``[start, end)``."""

    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Turn:
    """One conversation turn; ``id`` increases with insertion order."""

    id: int
    role: Role
    content: str
    created_at: datetime


@dataclass(frozen=True)
class Notification:
    """A queued notification for the agent loop (#71)."""

    id: int
    kind: str
    payload: JSON
    created_at: datetime


class NotesProvider(Protocol):
    async def create(self, title: str, body: str = "") -> Note: ...

    async def get(self, note_id: str) -> Note | None: ...

    async def find(self, *, query: str | None = None, limit: int = 100) -> list[Note]:
        """Most recently updated first; ``query`` matches title or body (case-insensitive)."""
        ...

    async def update(self, note: Note) -> Note: ...

    async def delete(self, note_id: str) -> bool: ...


class TodoProvider(Protocol):
    async def create(self, title: str, *, due: datetime | None = None) -> Todo: ...

    async def get(self, todo_id: str) -> Todo | None: ...

    async def find(self, *, include_done: bool = False, limit: int = 100) -> list[Todo]:
        """Open todos first, then by due date (undated last), then by creation."""
        ...

    async def update(self, todo: Todo) -> Todo: ...

    async def delete(self, todo_id: str) -> bool: ...


class CalendarProvider(Protocol):
    async def create(
        self,
        title: str,
        start: datetime,
        end: datetime,
        *,
        location: str | None = None,
        notes: str | None = None,
    ) -> Event: ...

    async def get(self, event_id: str) -> Event | None: ...

    async def between(self, start: datetime, end: datetime) -> list[Event]:
        """Events overlapping ``[start, end)``, ordered by start."""
        ...

    async def update(self, event: Event) -> Event: ...

    async def delete(self, event_id: str) -> bool: ...


class KeyValueStore(Protocol):
    """Preferences, capability config and caches; values are JSON."""

    async def get(self, key: str, default: JSON = None) -> JSON: ...

    async def set(self, key: str, value: JSON) -> None: ...

    async def delete(self, key: str) -> bool: ...

    async def keys(self, prefix: str = "") -> list[str]: ...


class ConversationMemory(Protocol):
    async def append(self, role: Role, content: str) -> Turn: ...

    async def recent(self, limit: int = 20) -> list[Turn]:
        """The last ``limit`` turns, oldest first (ready to feed to an LLM)."""
        ...

    async def clear(self) -> None: ...


class NotificationQueue(Protocol):
    async def push(self, kind: str, payload: JSON = None) -> Notification: ...

    async def pending(self, limit: int = 50) -> list[Notification]:
        """Unacknowledged notifications, oldest first."""
        ...

    async def ack(self, notification_id: int) -> bool: ...
