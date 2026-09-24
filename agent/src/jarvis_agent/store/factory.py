"""Open the state store and pick a provider per domain: local by default, Faelab on request.

Faelab providers are not built here: whoever connects to Faelab (capabilities, #72) passes
them in via ``FaelabProviders``. A domain configured as ``faelab`` without one is a config
error at startup, not a silent fallback to local data.
"""

from dataclasses import dataclass
from pathlib import Path

from jarvis_agent.store.base import (
    CalendarProvider,
    ConversationMemory,
    KeyValueStore,
    NotesProvider,
    NotificationQueue,
    StoreError,
    TodoProvider,
)
from jarvis_agent.store.config import StoreSettings
from jarvis_agent.store.local import (
    Clock,
    LocalCalendar,
    LocalConversationMemory,
    LocalKeyValue,
    LocalNotes,
    LocalNotificationQueue,
    LocalTodos,
    utc_now,
)
from jarvis_agent.store.sqlite import SqliteStore


class StoreConfigError(StoreError):
    """The configured providers can't be satisfied."""


@dataclass(frozen=True)
class FaelabProviders:
    """Remote providers for the overridable domains; ``None`` = not available."""

    notes: NotesProvider | None = None
    todo: TodoProvider | None = None
    calendar: CalendarProvider | None = None


@dataclass
class State:
    """Every state domain, plus snapshot/restore of the local database (#67).

    Snapshots cover only the local SQLite file; data served by Faelab is never in them.
    """

    notes: NotesProvider
    todo: TodoProvider
    calendar: CalendarProvider
    kv: KeyValueStore
    memory: ConversationMemory
    notifications: NotificationQueue
    db: SqliteStore

    async def snapshot(self, dest: str | Path) -> Path:
        return await self.db.snapshot(dest)

    async def restore(self, src: str | Path) -> None:
        await self.db.restore(src)

    async def aclose(self) -> None:
        await self.db.aclose()


async def open_state(
    settings: StoreSettings | None = None,
    *,
    faelab: FaelabProviders | None = None,
    clock: Clock = utc_now,
) -> State:
    settings = StoreSettings.from_env() if settings is None else settings
    faelab = FaelabProviders() if faelab is None else faelab
    remote = {
        domain: _faelab_provider(faelab, domain)
        for domain in ("notes", "todo", "calendar")
        if getattr(settings, domain) == "faelab"
    }
    db = await SqliteStore.open(settings.db)
    return State(
        notes=remote.get("notes") or LocalNotes(db, clock),
        todo=remote.get("todo") or LocalTodos(db, clock),
        calendar=remote.get("calendar") or LocalCalendar(db, clock),
        kv=LocalKeyValue(db, clock),
        memory=LocalConversationMemory(db, clock),
        notifications=LocalNotificationQueue(db, clock),
        db=db,
    )


def _faelab_provider(
    faelab: FaelabProviders, domain: str
) -> NotesProvider | TodoProvider | CalendarProvider:
    provider = getattr(faelab, domain)
    if provider is None:
        raise StoreConfigError(
            f"JARVIS_{domain.upper()}_PROVIDER=faelab, but no Faelab {domain} provider is "
            "available (Faelab providers are not implemented yet, see #72)"
        )
    return provider
