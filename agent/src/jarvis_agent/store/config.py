"""State store settings from environment variables (minimal; the full schema is #73)::

    JARVIS_STATE_DB            SQLite file, or :memory:   (default: /data/jarvis.db)
    JARVIS_NOTES_PROVIDER      local | faelab             (default: local)
    JARVIS_TODO_PROVIDER       local | faelab             (default: local)
    JARVIS_CALENDAR_PROVIDER   local | faelab             (default: local)

Only notes, todo and calendar can move to Faelab; memory, preferences, notifications and
caches are Jarvis-owned and always local. Empty values count as unset.
"""

import os
from collections.abc import Mapping
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict

ProviderKind = Literal["local", "faelab"]
DOMAINS = ("notes", "todo", "calendar")
DEFAULT_DB = "/data/jarvis.db"


class StoreSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    db: str = DEFAULT_DB
    notes: ProviderKind = "local"
    todo: ProviderKind = "local"
    calendar: ProviderKind = "local"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        values = {"db": env.get("JARVIS_STATE_DB", "").strip()}
        for domain in DOMAINS:
            values[domain] = env.get(f"JARVIS_{domain.upper()}_PROVIDER", "").strip().lower()
        return cls(**{name: value for name, value in values.items() if value})
