"""Configure stdlib ``logging`` once: root -> a queue -> a listener thread -> stderr + file.

The only handler on the calling side is a ``QueueHandler`` that never blocks: a full queue
drops the record (counted in ``dropped``) rather than stall the voice loop. Uvicorn's
loggers are rerouted through the same handlers and format.
"""

import copy
import logging
import queue
import sys
from dataclasses import dataclass, field
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import TextIO

from jarvis_agent.logs.config import LogSettings
from jarvis_agent.logs.files import DailyFileHandler
from jarvis_agent.logs.format import PACKAGE_PREFIX, LineFormatter, enrich, parse_level

QUEUE_SIZE = 10_000
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")
# Applied before the configured ``levels``. Library DEBUG is protocol noise (and would
# log user text, which the spec allows only at TRACE); a health check every 10s and each
# HTTP call to a model server are not INFO events.
DEFAULT_LEVELS = {
    "uvicorn": "INFO",
    "uvicorn.access": "WARN",
    "websockets": "INFO",
    "httpx": "WARN",
    "httpcore": "INFO",
}


class StderrHandler(logging.StreamHandler[TextIO]):
    """Writes to whatever ``sys.stderr`` is at the time (test capture swaps it)."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)

    @property  # type: ignore[override]
    def stream(self) -> TextIO:
        return sys.stderr

    @stream.setter
    def stream(self, _value: object) -> None:
        pass


class DroppingQueueHandler(QueueHandler):
    """Hands records to the listener thread. Never blocks and never formats: the listener
    formats. Only what must be read now is fixed here (the args, the trace id)."""

    def __init__(self, q: queue.Queue[logging.LogRecord]) -> None:
        super().__init__(q)
        self.dropped = 0

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        record = copy.copy(record)
        enrich(record)  # trace id from this thread's context, error.type
        record.msg = record.getMessage()  # args may change once we return
        record.args = None
        if record.exc_info:  # tracebacks hold frames: render them now, not later
            record.exc_text = LineFormatter().formatException(record.exc_info)
            record.exc_info = None
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1


@dataclass
class Logging:
    """What ``configure()`` installed; ``stop()`` flushes the queue and undoes it."""

    handler: DroppingQueueHandler
    listener: QueueListener
    file: DailyFileHandler | None
    _levels: dict[str, int] = field(default_factory=dict)  # logger -> level before
    _uvicorn: dict[str, tuple[list[logging.Handler], bool]] = field(default_factory=dict)

    def stop(self) -> None:
        root = logging.getLogger()
        root.removeHandler(self.handler)
        self.listener.stop()  # drains what is queued
        for handler in self.listener.handlers:
            handler.close()
        for name, level in self._levels.items():
            logging.getLogger(name if name else None).setLevel(level)
        for name, (handlers, propagate) in self._uvicorn.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.propagate = propagate


_active: Logging | None = None


def configure(
    settings: LogSettings | None = None,
    *,
    version: str = "unknown",
    stderr: bool = True,
    extra_handlers: list[logging.Handler] | None = None,
) -> Logging:
    """Install the handlers (replacing an earlier ``configure``) and start the listener."""
    global _active
    shutdown()
    settings = settings or LogSettings()
    handlers: list[logging.Handler] = []
    if stderr:
        handlers.append(StderrHandler())
        handlers[-1].setFormatter(LineFormatter())
    file = None
    if settings.dir:
        file = DailyFileHandler(
            Path(settings.dir), version=version, daily_cap_mb=settings.daily_cap_mb
        )
        handlers.append(file)
    handlers += extra_handlers or []

    q: queue.Queue[logging.LogRecord] = queue.Queue(QUEUE_SIZE)
    handler = DroppingQueueHandler(q)
    listener = QueueListener(q, *handlers, respect_handler_level=True)
    installed = Logging(handler, listener, file)

    root = logging.getLogger()
    installed._levels[""] = root.level
    root.setLevel(parse_level(settings.level))
    for name in UVICORN_LOGGERS:  # uvicorn's own dictConfig gave them handlers
        logger = logging.getLogger(name)
        installed._uvicorn[name] = (list(logger.handlers), logger.propagate)
        installed._levels.setdefault(name, logger.level)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)
    for name, level in (DEFAULT_LEVELS | settings.levels).items():
        for full in _logger_names(name):
            logger = logging.getLogger(full)
            installed._levels.setdefault(full, logger.level)
            logger.setLevel(parse_level(level))

    listener.start()
    root.addHandler(handler)
    _active = installed
    return installed


def shutdown() -> None:
    """Flush and remove what ``configure()`` installed. Idempotent."""
    global _active
    if _active is not None:
        active, _active = _active, None
        active.stop()


def active() -> Logging | None:
    return _active


def _logger_names(name: str) -> list[str]:
    """A ``levels`` key names a logger as it shows in the line (``loop.voice``) or in full
    (``jarvis_agent.loop.voice``, ``uvicorn.access``)."""
    return [name] if name.startswith(PACKAGE_PREFIX) else [PACKAGE_PREFIX + name, name]
