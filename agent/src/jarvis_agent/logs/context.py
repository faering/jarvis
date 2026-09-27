"""The trace id of the current turn or request, in a context variable.

asyncio tasks copy the context when they are created, so a task started inside
``traced()`` (or with ``context=`` a context holding the id) logs with that turn's id.
"""

import contextvars
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "jarvis_trace_id", default=None
)

NO_TURN = "--------"


def new_trace_id() -> str:
    """A W3C trace id: 32 lowercase hex chars."""
    return secrets.token_hex(16)


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def set_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    """Set the id for the current context; undo with ``reset_trace_id(token)``."""
    return _TRACE_ID.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    _TRACE_ID.reset(token)


@contextmanager
def traced(trace_id: str | None = None) -> Iterator[str]:
    """Run the block under ``trace_id`` (a new one if None); yields the id."""
    trace_id = trace_id or new_trace_id()
    token = _TRACE_ID.set(trace_id)
    try:
        yield trace_id
    finally:
        _TRACE_ID.reset(token)


def trace_context(trace_id: str | None) -> contextvars.Context:
    """A copy of the current context with ``trace_id`` set: pass it as
    ``asyncio.create_task(..., context=...)`` to run a task under that id."""
    context = contextvars.copy_context()
    context.run(_TRACE_ID.set, trace_id)
    return context


def turn_slot(trace_id: str | None) -> str:
    """The line's turn slot: the id's first 8 chars, or ``--------``."""
    return trace_id[:8] if trace_id else NO_TURN
