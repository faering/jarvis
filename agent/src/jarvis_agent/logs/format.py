"""The line format of docs/logging.md, OTel level names and secret redaction.

``[2026-09-27 15:44:38.101Z] [INFO ] [agent] [loop.voice] [4bf92f35] turn started  k=v``
"""

import logging
import os
import re
import time
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from jarvis_agent.logs.context import current_trace_id, turn_slot

TRACE = 5
logging.addLevelName(TRACE, "TRACE")  # uvicorn registers the same name for 5

# Python level -> OTel SeverityText. Levels in between take the name below them.
LEVEL_TEXT = {TRACE: "TRACE", 10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}
# Config level name -> Python level (OTel and Python spellings both accepted).
LEVELS = {
    "TRACE": TRACE,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "FATAL": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,
}

COMPONENT = "agent"
PACKAGE_PREFIX = "jarvis_agent."
REDACTED = "[REDACTED]"
ATTRIBUTES = "attributes"  # the LogRecord attribute holding key=value pairs
_UNSET = object()


def kv(**attributes: Any) -> dict[str, dict[str, Any]]:
    """Attributes for one record: ``log.info("transcribed", extra=kv(duration_ms=312))``.

    Dotted OTel keys (``error.type``) go through a dict: ``extra=kv(**{"error.type": ...})``.
    """
    return {ATTRIBUTES: attributes}


def level_text(levelno: int) -> str:
    name = "TRACE"
    for number, text in LEVEL_TEXT.items():
        if levelno >= number:
            name = text
    return name


def parse_level(name: str) -> int:
    """``"warn"`` -> 30; raises ``ValueError`` for an unknown name."""
    try:
        return LEVELS[name.strip().upper()]
    except KeyError:
        known = ", ".join(LEVEL_TEXT.values())
        raise ValueError(f"unknown log level {name!r} (use {known})") from None


def logger_slot(name: str) -> str:
    return name.removeprefix(PACKAGE_PREFIX)


# ---- redaction --------------------------------------------------------------------------

_SECRET_PARTS = {
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "key",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
}
_SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1 " + REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), REDACTED),
    (
        re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd)([\"']?\s*[=:]\s*)[^\s,;&]+"),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"://[^/\s:@]+:[^/\s@]+@"), "://" + REDACTED + "@"),  # user:pass in URLs
]


def is_secret_key(key: str) -> bool:
    """``api_key``, ``auth.token``, ``Authorization``... (split on ``.``, ``_``, ``-``)."""
    parts = re.split(r"[._-]", key.lower())
    return any(p in _SECRET_PARTS for p in parts) or "api_key" in key.lower()


def scrub(text: str) -> str:
    """Mask obvious secrets (bearer tokens, ``sk-...`` keys, ``token=...``) in free text."""
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


# ---- values -----------------------------------------------------------------------------


def render_value(key: str, value: Any) -> str:
    """One attribute value, quoted when it holds a space, ``=``, ``"`` or is empty."""
    if isinstance(value, SecretStr) or is_secret_key(key):
        return REDACTED
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = scrub(str(value))
    if text == "" or any(c in text for c in ' ="\n\r\t'):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{escaped}"'
    return text


def render_attributes(attributes: Mapping[str, Any]) -> str:
    return " ".join(f"{key}={render_value(key, value)}" for key, value in attributes.items())


def relative_path(path: str) -> str:
    """``/…/site-packages/jarvis_agent/loop/voice.py`` -> ``jarvis_agent/loop/voice.py``."""
    normalized = path.replace(os.sep, "/")
    for marker in ("/jarvis_agent/", "/site-packages/"):
        if (at := normalized.rfind(marker)) >= 0:
            return normalized[at + 1 :] if marker == "/jarvis_agent/" else normalized[at + 15 :]
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


_TRACEBACK_FILE = re.compile(r'File "([^"]+)"')


def enrich(record: logging.LogRecord) -> None:
    """Fix what must be read in the logging thread: the trace id (a context variable) and,
    for an exception, ``error.type``. Idempotent."""
    if getattr(record, "trace_id", _UNSET) is _UNSET:
        record.trace_id = current_trace_id()
    if record.exc_info and record.exc_info[1] is not None:
        attributes = getattr(record, ATTRIBUTES, None) or {}
        if "error.type" not in attributes:
            record.__dict__[ATTRIBUTES] = {
                **attributes,
                "error.type": type(record.exc_info[1]).__name__,
            }


class LineFormatter(logging.Formatter):
    """Formats a record as one spec line, plus indented continuation lines for ERROR/FATAL
    (``at <file>:<line> in <func>``, where it was logged) and any traceback."""

    def __init__(self, component: str = COMPONENT) -> None:
        super().__init__()
        self.component = component

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        seconds = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(record.created))
        return f"{seconds}.{int(record.msecs):03d}Z"

    def format(self, record: logging.LogRecord) -> str:
        enrich(record)
        message = scrub(record.getMessage()).replace("\n", "\\n").replace("\r", "\\r")
        line = (
            f"[{self.formatTime(record)}] [{level_text(record.levelno):<5}] [{self.component}]"
            f" [{logger_slot(record.name)}] [{turn_slot(record.trace_id)}] {message}"
        )
        if attributes := getattr(record, ATTRIBUTES, None):
            line += "  " + render_attributes(attributes)
        extra: list[str] = []
        if record.levelno >= logging.ERROR:
            extra.append(
                f"at {relative_path(record.pathname)}:{record.lineno} in {record.funcName}"
            )
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        for block in (record.exc_text, record.stack_info):
            if block:
                block = _TRACEBACK_FILE.sub(lambda m: f'File "{relative_path(m[1])}"', block)
                extra.extend(scrub(block).splitlines())
        return "\n    ".join([line, *extra])
