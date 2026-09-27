"""The daily log file: ``<dir>/jarvis-agent-YYYY-MM-DD.log``, one per UTC day, with a cap.

Runs in the queue listener's thread, never on the event loop. The day comes from each
record's timestamp, so the file switches at UTC midnight. At the daily cap only WARN and
above are written (plus one ERROR saying so); at 110% nothing more until the next day.
Old files are never deleted here: ``jarvis-logs prune`` on the Pi does that.
"""

import logging
import os
import sys
import time
from pathlib import Path

from jarvis_agent.logs.format import COMPONENT, LineFormatter

MIB = 1024 * 1024
FILE_MODE = 0o640
HARD_CAP = 1.10  # stop writing at 110% of the daily cap


class DailyFileHandler(logging.Handler):
    def __init__(
        self,
        directory: Path,
        *,
        version: str,
        daily_cap_mb: int = 500,
        component: str = COMPONENT,
        formatter: logging.Formatter | None = None,
    ) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.version = version
        self.component = component
        self.cap = daily_cap_mb * MIB
        self.setFormatter(formatter or LineFormatter(component))
        self._fd: int | None = None
        self._day: str | None = None
        self._size = 0
        self._capped = False  # the "cap reached" ERROR was written

    def path_for(self, day: str) -> Path:
        return self.directory / f"jarvis-{self.component}-{day}.log"

    @property
    def path(self) -> Path | None:
        return self.path_for(self._day) if self._day else None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = time.strftime("%Y-%m-%d", time.gmtime(record.created))
            if day != self._day:
                self._open(day, record)
            if self._fd is None or self._size >= self.cap * HARD_CAP:
                return
            if self._size >= self.cap:
                if not self._capped:
                    self._capped = True
                    message = "daily log cap reached, keeping WARN and above until the next day"
                    self._write(self._note(record, logging.ERROR, message, cap_mb=self.cap // MIB))
                if record.levelno < logging.WARNING:
                    return
            self._write(self.format(record))
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self.lock:
            self._close_fd()
        super().close()

    def _open(self, day: str, record: logging.LogRecord) -> None:
        """Open the day's file; if that fails, say so once on stderr and skip the day."""
        self._close_fd()
        self._day = day
        path = self.path_for(day)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            created = not path.exists()
            self._fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
            if created:
                os.fchmod(self._fd, FILE_MODE)  # the umask may have taken group read away
        except OSError as exc:
            print(f"jarvis: cannot open log file {path}: {exc}", file=sys.stderr)
            return
        self._size = os.fstat(self._fd).st_size  # a restart the same day keeps counting
        self._capped = False
        header = {"service.version": self.version, "pid": os.getpid()}
        self._write(self._note(record, logging.INFO, "log opened", **header))

    def _note(self, record: logging.LogRecord, level: int, msg: str, **attributes: object) -> str:
        """A line of the handler's own (logger ``log``), timed like ``record``."""
        caller = sys._getframe(1)
        note = logging.makeLogRecord(
            {
                "name": "log",
                "levelno": level,
                "levelname": logging.getLevelName(level),
                "msg": msg,
                "created": record.created,
                "msecs": record.msecs,
                "trace_id": None,
                "pathname": __file__,
                "lineno": caller.f_lineno,
                "funcName": caller.f_code.co_name,
                "attributes": attributes,
            }
        )
        return self.format(note)

    def _write(self, line: str) -> None:
        assert self._fd is not None
        data = (line + "\n").encode("utf-8", "replace")
        os.write(self._fd, data)
        self._size += len(data)

    def _close_fd(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
