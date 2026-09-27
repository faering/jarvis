"""Agent logging per docs/logging.md, on the stdlib ``logging`` module.

- ``configure(settings, version=...)`` once at startup, ``shutdown()`` at exit.
- Attributes: ``log.info("transcribed", extra=kv(duration_ms=312))``.
- TRACE: ``log.log(TRACE, "heard text", extra=kv(text=text))``.
- Turns: ``with traced() as trace_id:`` (or ``trace_context(id)`` for a task); lines
  logged inside carry the id's 8-char prefix.
"""

from jarvis_agent.logs.config import LogSettings
from jarvis_agent.logs.context import (
    current_trace_id,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
    trace_context,
    traced,
)
from jarvis_agent.logs.files import DailyFileHandler
from jarvis_agent.logs.format import TRACE, LineFormatter, kv, parse_level, scrub
from jarvis_agent.logs.setup import active, configure, shutdown

__all__ = [
    "TRACE",
    "DailyFileHandler",
    "LineFormatter",
    "LogSettings",
    "active",
    "configure",
    "current_trace_id",
    "kv",
    "new_trace_id",
    "parse_level",
    "reset_trace_id",
    "scrub",
    "set_trace_id",
    "shutdown",
    "trace_context",
    "traced",
]
