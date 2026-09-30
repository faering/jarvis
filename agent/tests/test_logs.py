"""Logging (docs/logging.md): line format, levels, redaction, trace ids, files, queue."""

import asyncio
import logging
import os
import stat
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from jarvis_agent import logs
from jarvis_agent.config import ConfigError, load_config
from jarvis_agent.logs import TRACE, DailyFileHandler, LineFormatter, LogSettings, kv, traced
from jarvis_agent.logs import setup as log_setup
from jarvis_agent.logs.format import level_text, parse_level, render_value, scrub
from jarvis_agent.runtime import log_settings

FIXTURE = Path(__file__).parents[2] / "docs" / "logging-examples.log"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


def record(
    when: str,
    level: int,
    name: str,
    msg: str,
    *,
    attributes: dict[str, Any] | None = None,
    trace_id: str | None = None,
    **fields: Any,
) -> logging.LogRecord:
    """A record as logged at ``when`` (``2026-09-27 15:44:38.101``, UTC)."""
    rec = logging.LogRecord(name, level, fields.pop("pathname", __file__), 1, msg, None, None)
    at = datetime.strptime(when, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    rec.created = at.timestamp()
    rec.msecs = at.microsecond // 1000
    rec.trace_id = trace_id
    rec.attributes = attributes or {}
    rec.__dict__.update(fields)
    return rec


@pytest.fixture(autouse=True)
def _no_leftover_logging() -> Iterator[None]:
    yield
    logs.shutdown()


# ---- the shared fixture ----------------------------------------------------------------


def _fixture_records(component: str) -> list[str]:
    """The fixture's records (with continuation lines) of one component."""
    records: list[str] = []
    for line in FIXTURE.read_text().splitlines():
        if line.startswith("["):
            records.append(line)
        elif records:
            records[-1] += "\n" + line
    return [r for r in records if r.split("] [")[2] == component]


AGENT_RECORDS = [
    record(
        "2026-09-27 15:44:38.000",
        logging.INFO,
        "log",
        "log opened",
        attributes={"service.version": "0.2.0", "pid": 1},
    ),
    record(
        "2026-09-27 15:44:38.101",
        logging.INFO,
        "jarvis_agent.voice.loop",
        "turn started",
        attributes={"trace_id": TRACE_ID, "source": "wake_word"},
        trace_id=TRACE_ID,
    ),
    record(
        "2026-09-27 15:44:38.200",
        TRACE,
        "jarvis_agent.voice.stt",
        "heard text",
        attributes={"text": "what's the weather today?"},
        trace_id=TRACE_ID,
    ),
    record(
        "2026-09-27 15:44:38.435",
        logging.DEBUG,
        "jarvis_agent.voice.stt",
        "transcribed",
        attributes={"duration_ms": 312, "chars": 27},
        trace_id=TRACE_ID,
    ),
    record(
        "2026-09-27 15:44:39.301",
        logging.WARNING,
        "jarvis_agent.routing",
        "slow first token, falling back",
        attributes={"backend": "local", "latency_ms": 2100},
        trace_id=TRACE_ID,
    ),
    record(
        "2026-09-27 15:44:39.500",
        logging.INFO,
        "jarvis_agent.routing",
        "reply ready\nsecond line kept on one line",
        attributes={"note": 'has "quotes" and a \\ backslash', "empty": ""},
        trace_id=TRACE_ID,
    ),
    record(
        "2026-09-27 15:44:40.002",
        logging.ERROR,
        "jarvis_agent.speech.tts",
        "synthesis failed",
        attributes={"error.type": "TimeoutError"},
        trace_id=TRACE_ID,
        pathname="/usr/local/lib/python3.14/site-packages/jarvis_agent/speech/tts.py",
        lineno=88,
        funcName="synthesize",
        exc_text=(
            "Traceback (most recent call last):\n"
            '  File "/app/agent/src/jarvis_agent/speech/tts.py", line 88, in synthesize\n'
            "TimeoutError: speaches did not answer in 5.0s"
        ),
    ),
]


def test_formatter_reproduces_every_agent_line_of_the_fixture() -> None:
    formatter = LineFormatter()
    assert [formatter.format(r) for r in AGENT_RECORDS] == _fixture_records("agent")


def test_error_without_exception_still_says_where() -> None:
    rec = record(
        "2026-09-27 16:02:12.000",
        logging.CRITICAL,
        "jarvis_agent.main",
        "cannot start: display not found",
        pathname="/app/agent/src/jarvis_agent/main.py",
        lineno=42,
        funcName="main",
    )
    assert LineFormatter().format(rec) == (
        "[2026-09-27 16:02:12.000Z] [FATAL] [agent] [main] [--------] cannot start: display"
        " not found\n    at jarvis_agent/main.py:42 in main"
    )


def test_a_real_exception_is_rendered_with_its_type() -> None:
    log = logging.getLogger("jarvis_agent.test")
    try:
        raise TimeoutError("slow")
    except TimeoutError:
        rec = log.makeRecord(
            log.name, logging.ERROR, __file__, 7, "failed", None, sys.exc_info(), func="fn"
        )
    lines = LineFormatter().format(rec).splitlines()
    assert lines[0].endswith("[test] [--------] failed  error.type=TimeoutError")
    assert lines[1] == f"    at {os.path.relpath(__file__)}:7 in fn"
    assert lines[2] == "    Traceback (most recent call last):"
    assert lines[-1] == "    TimeoutError: slow"
    assert all(line.startswith("    ") for line in lines[1:])


# ---- levels, quoting, redaction --------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "text"),
    [(5, "TRACE"), (10, "DEBUG"), (20, "INFO"), (25, "INFO"), (30, "WARN"), (40, "ERROR")]
    + [(50, "FATAL"), (1, "TRACE")],
)
def test_levels_use_otel_names(level: int, text: str) -> None:
    assert level_text(level) == text


def test_level_names_parse_in_either_spelling() -> None:
    assert parse_level("warn") == parse_level("WARNING") == logging.WARNING
    assert parse_level("fatal") == parse_level("critical") == logging.CRITICAL
    assert parse_level("trace") == TRACE == 5
    with pytest.raises(ValueError, match="unknown log level"):
        parse_level("loud")


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (312, "312"),
        ("local", "local"),
        ("two words", '"two words"'),
        ("a=b", '"a=b"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("", '""'),
        (None, '""'),
        (True, "true"),
        ("line\nbreak", '"line\\nbreak"'),
        ('back\\slash "q"', '"back\\\\slash \\"q\\""'),
    ],
)
def test_attribute_values_are_quoted_per_spec(value: object, text: str) -> None:
    assert render_value("k", value) == text


@pytest.mark.parametrize(
    "key", ["api_key", "token", "auth.token", "Authorization", "password", "client_secret", "key"]
)
def test_secret_attribute_keys_are_redacted(key: str) -> None:
    assert render_value(key, "hunter2") == "[REDACTED]"


def test_secret_values_and_messages_are_redacted() -> None:
    assert render_value("backend", SecretStr("x")) == "[REDACTED]"
    for keep in ("duration_ms", "trace_id", "tokens", "input_tokens"):
        assert render_value(keep, "v") == "v"
    text = scrub(
        "Authorization: Bearer abc.def-123 key sk-proj-ABCDEFGH12345 api_key=zzz"
        " https://user:pw@host/x password: letmein"
    )
    assert text == (
        "Authorization: Bearer [REDACTED] key [REDACTED] api_key=[REDACTED]"
        " https://[REDACTED]@host/x password: [REDACTED]"
    )


def test_redaction_applies_to_formatted_lines() -> None:
    rec = record(
        "2026-09-27 15:44:38.000",
        logging.WARNING,
        "jarvis_agent.backends",
        "retry with Bearer s3cr3t",
        attributes={"api_key": "sk-abcdefghijk", "url": "http://a:b@host"},
    )
    line = LineFormatter().format(rec)
    assert "s3cr3t" not in line and "sk-abc" not in line and "a:b@" not in line
    assert line.endswith(
        "retry with Bearer [REDACTED]  api_key=[REDACTED] url=http://[REDACTED]@host"
    )


# ---- trace context ---------------------------------------------------------------------


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(LineFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _configure(**settings: Any) -> ListHandler:
    sink = ListHandler()
    logs.configure(LogSettings(**settings), stderr=False, extra_handlers=[sink])
    return sink


def test_trace_id_follows_the_context_across_the_queue_thread() -> None:
    sink = _configure()
    log = logging.getLogger("jarvis_agent.loop.voice")

    async def turn() -> None:
        log.info("inside")

    async def main() -> str:
        with traced() as trace_id:
            await asyncio.create_task(turn())  # tasks inherit the context
        log.info("outside")
        return trace_id

    trace_id = asyncio.run(main())
    logs.shutdown()  # drains the queue
    assert len(trace_id) == 32 and int(trace_id, 16) >= 0
    assert f"[loop.voice] [{trace_id[:8]}] inside" in sink.lines[0]
    assert "[loop.voice] [--------] outside" in sink.lines[1]


def test_logging_never_blocks_the_caller() -> None:
    release = threading.Event()

    class Stuck(ListHandler):  # a disk that hangs
        def emit(self, record: logging.LogRecord) -> None:
            release.wait(5)
            super().emit(record)

    stuck = Stuck()
    logs.configure(LogSettings(), stderr=False, extra_handlers=[stuck])
    log = logging.getLogger("jarvis_agent.loop.voice")

    async def hot_path() -> float:
        started = time.monotonic()
        for i in range(200):
            log.info("tick", extra=kv(i=i))
        return time.monotonic() - started

    assert asyncio.run(hot_path()) < 0.5  # the handler is stuck, the loop is not
    release.set()
    logs.shutdown()
    assert len(stuck.lines) == 200
    assert stuck.lines[-1].endswith("tick  i=199")


def test_a_full_queue_drops_instead_of_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()

    class Stuck(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            release.wait(5)

    monkeypatch.setattr(log_setup, "QUEUE_SIZE", 5)
    installed = logs.configure(LogSettings(), stderr=False, extra_handlers=[Stuck()])
    for _ in range(50):
        logging.getLogger("jarvis_agent.x").warning("flood")
    assert installed.handler.dropped >= 40
    release.set()


def test_shutdown_drains_a_full_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    """#233: stopping with the queue full used to raise queue.Full instead of draining."""
    started, release = threading.Event(), threading.Event()
    emitted: list[str] = []

    class Stuck(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            started.set()
            release.wait(5)
            emitted.append(record.getMessage())

    monkeypatch.setattr(log_setup, "QUEUE_SIZE", 5)
    installed = logs.configure(LogSettings(), stderr=False, extra_handlers=[Stuck()])
    log = logging.getLogger("jarvis_agent.x")
    log.warning("first")
    assert started.wait(5)  # the listener holds "first": the queue is empty again
    for i in range(20):
        log.warning("line %d", i)  # 5 fit, the rest are dropped
    assert installed.handler.queue.full()  # type: ignore[attr-defined]
    errors: list[BaseException] = []

    def stop() -> None:
        try:
            logs.shutdown()
        except BaseException as exc:  # noqa: BLE001 - the test reports it
            errors.append(exc)

    stopper = threading.Thread(target=stop)
    stopper.start()
    release.set()
    stopper.join(5)
    assert not stopper.is_alive()
    assert errors == []
    assert emitted == ["first", *(f"line {i}" for i in range(5))]


# ---- configuration ---------------------------------------------------------------------


def test_levels_come_from_settings_with_per_logger_overrides() -> None:
    sink = _configure(level="WARN", levels={"loop.voice": "DEBUG", "uvicorn.access": "INFO"})
    logging.getLogger("jarvis_agent.loop.voice").debug("kept")
    logging.getLogger("jarvis_agent.routing.router").info("dropped")
    logging.getLogger("jarvis_agent.routing.router").warning("kept too")
    logging.getLogger("uvicorn.access").info("GET /health")
    logs.shutdown()
    assert [line.split("] ", 5)[5] for line in sink.lines] == ["kept", "kept too", "GET /health"]
    assert logging.getLogger("jarvis_agent.loop.voice").level == logging.NOTSET  # restored


def test_uvicorn_goes_through_the_same_handlers_and_is_restored() -> None:
    uvicorn = logging.getLogger("uvicorn.error")
    own = logging.NullHandler()
    uvicorn.addHandler(own)
    uvicorn.propagate = False
    try:
        sink = _configure()
        assert uvicorn.handlers == [] and uvicorn.propagate
        uvicorn.info("Started server process [%d]", 1)
        logs.shutdown()
        assert sink.lines[0].endswith("[uvicorn.error] [--------] Started server process [1]")
        assert uvicorn.handlers == [own] and not uvicorn.propagate
    finally:
        uvicorn.removeHandler(own)
        uvicorn.propagate = True


def test_config_section_and_env(tmp_path: Path) -> None:
    local = tmp_path / "jarvis.toml"
    local.write_text(
        '[logging]\nlevel = "debug"\ndaily_cap_mb = 50\n[logging.levels]\n"voice.stt" = "trace"\n'
    )
    config = load_config({"JARVIS_CONFIG": str(local), "JARVIS_LOG_DIR": "/var/log/jarvis"})
    assert config.logging == LogSettings(
        dir="/var/log/jarvis", level="DEBUG", levels={"voice.stt": "TRACE"}, daily_cap_mb=50
    )
    env = {"JARVIS_CONFIG": str(local), "JARVIS_LOG_LEVEL": "warning", "JARVIS_LOG_DIR": ""}
    assert load_config(env).logging.level == "WARN"  # env wins; empty = unset
    assert load_config({}).logging == LogSettings()  # stderr only, INFO, 500 MiB
    with pytest.raises(ConfigError, match="logging.level"):
        load_config({"JARVIS_LOG_LEVEL": "loud"})


def test_dev_profile_logs_debug() -> None:
    assert load_config({"JARVIS_PROFILE": "dev"}).logging.level == "DEBUG"


def test_an_invalid_config_still_gets_logging_from_env(tmp_path: Path) -> None:
    local = tmp_path / "jarvis.toml"
    local.write_text('hardware = "broken"\n')
    env = {"JARVIS_CONFIG": str(local), "JARVIS_LOG_DIR": "/tmp/x", "JARVIS_LOG_LEVEL": "debug"}
    settings, problems = log_settings(env)
    assert settings == LogSettings(dir="/tmp/x", level="DEBUG")
    assert problems


# ---- daily files -----------------------------------------------------------------------


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def test_daily_file_switches_at_utc_midnight(tmp_path: Path) -> None:
    handler = DailyFileHandler(tmp_path / "logs", version="1.2.3")
    name = "jarvis_agent.loop.voice"
    handler.handle(record("2026-09-27 23:59:59.999", logging.INFO, name, "late"))
    handler.handle(record("2026-09-28 00:00:00.000", logging.INFO, name, "early"))
    handler.close()

    day1 = tmp_path / "logs" / "jarvis-agent-2026-09-27.log"
    day2 = tmp_path / "logs" / "jarvis-agent-2026-09-28.log"
    for path, message in ((day1, "late"), (day2, "early")):
        header, line = _lines(path)
        assert (
            header.startswith(f"[{path.stem[-10:]} ") and "[log] [--------] log opened  " in header
        )
        assert header.endswith(" service.version=1.2.3 pid=" + header.rsplit("=", 1)[1])
        assert line.endswith(f"[loop.voice] [--------] {message}")
        assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_daily_cap_keeps_warnings_then_stops(tmp_path: Path) -> None:
    handler = DailyFileHandler(tmp_path, version="1")
    handler.cap = 10_000  # bytes, for the test
    name = "jarvis_agent.x"
    day = "2026-09-27 12:00:00.000"
    while handler._size < handler.cap:  # fill to the cap with INFO
        handler.handle(record(day, logging.INFO, name, "info " + "x" * 50))
    size = handler._size
    handler.handle(record(day, logging.INFO, name, "info-below-cap"))
    handler.handle(record(day, logging.WARNING, name, "warning kept"))
    while handler._size < handler.cap * 1.1:
        handler.handle(record(day, logging.ERROR, name, "error kept"))
    handler.handle(record(day, logging.CRITICAL, name, "fatal-past-hard-cap"))
    handler.handle(record("2026-09-28 00:00:00.000", logging.INFO, name, "new day"))
    handler.close()

    text = (tmp_path / "jarvis-agent-2026-09-27.log").read_text()
    assert size >= 10_000
    assert "info-below-cap" not in text and "fatal-past-hard-cap" not in text
    assert "warning kept" in text
    assert text.count("daily log cap reached") == 1
    assert "[ERROR] [agent] [log] [--------] daily log cap reached" in text
    assert "new day" in (tmp_path / "jarvis-agent-2026-09-28.log").read_text()


def test_a_restart_keeps_counting_the_days_file(tmp_path: Path) -> None:
    rec = record("2026-09-27 12:00:00.000", logging.INFO, "jarvis_agent.x", "hello")
    for _ in range(2):
        handler = DailyFileHandler(tmp_path, version="1")
        handler.handle(rec)
        handler.close()
    lines = _lines(tmp_path / "jarvis-agent-2026-09-27.log")
    assert len(lines) == 4 and handler._size == sum(len(line) + 1 for line in lines)


def test_configure_with_a_dir_writes_the_file(tmp_path: Path) -> None:
    logs.configure(LogSettings(dir=str(tmp_path)), version="9.9.9", stderr=False)
    logging.getLogger("jarvis_agent.runtime").info("agent ready")
    logs.shutdown()
    (path,) = tmp_path.glob("jarvis-agent-*.log")
    header, line = _lines(path)
    assert "log opened  service.version=9.9.9" in header
    assert line.endswith("[runtime] [--------] agent ready")


def test_an_unwritable_folder_is_reported_once_and_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("")
    handler = DailyFileHandler(blocked, version="1")
    for _ in range(3):
        handler.handle(record("2026-09-27 12:00:00.000", logging.INFO, "jarvis_agent.x", "hi"))
    handler.close()
    assert capsys.readouterr().err.count("cannot open log file") == 1
