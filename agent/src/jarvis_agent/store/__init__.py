"""Local persistent state: notes, todos, calendar, preferences, memory, notifications.

Open everything with ``open_state()`` (configured from ``JARVIS_STATE_DB`` and
``JARVIS_<DOMAIN>_PROVIDER``; see ``config``). All data lives in one SQLite file that can be
snapshotted and restored around a release promote/rollback (#67).
"""

from jarvis_agent.store.base import (
    CalendarProvider,
    ConversationMemory,
    Event,
    KeyValueStore,
    Note,
    NotesProvider,
    NotFoundError,
    Notification,
    NotificationQueue,
    StoreError,
    Todo,
    TodoProvider,
    Turn,
)
from jarvis_agent.store.config import StoreSettings
from jarvis_agent.store.factory import FaelabProviders, State, StoreConfigError, open_state
from jarvis_agent.store.sqlite import SCHEMA_VERSION, SqliteStore

__all__ = [
    "SCHEMA_VERSION",
    "CalendarProvider",
    "ConversationMemory",
    "Event",
    "FaelabProviders",
    "KeyValueStore",
    "Note",
    "NotFoundError",
    "NotesProvider",
    "Notification",
    "NotificationQueue",
    "SqliteStore",
    "State",
    "StoreConfigError",
    "StoreError",
    "StoreSettings",
    "Todo",
    "TodoProvider",
    "Turn",
    "open_state",
]
