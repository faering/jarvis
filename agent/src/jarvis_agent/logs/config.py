"""The ``[logging]`` config section (docs/logging.md, "Agent configuration")."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jarvis_agent.logs.format import LEVEL_TEXT, parse_level


def _level_name(value: str) -> str:
    return LEVEL_TEXT[parse_level(value)]


class LogSettings(BaseModel):
    """``dir``: the log folder (None = stderr only). ``level``: the root level.
    ``levels``: per-logger overrides, keyed by the name in the line (``loop.voice``) or the
    full logger name (``uvicorn.access``). ``daily_cap_mb``: the per-day file cap."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dir: str | None = None
    level: str = "INFO"
    levels: dict[str, str] = {}
    daily_cap_mb: int = Field(default=500, gt=0)

    @field_validator("dir")
    @classmethod
    def _empty_is_unset(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        return _level_name(value)

    @field_validator("levels")
    @classmethod
    def _known_levels(cls, value: dict[str, str]) -> dict[str, str]:
        return {name: _level_name(level) for name, level in value.items()}
