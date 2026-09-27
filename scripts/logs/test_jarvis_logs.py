"""Tests for scripts/logs/jarvis-logs and the bash writer scripts/lib/log.sh (stdlib only).

Run: python3 -m unittest discover -s scripts/logs
"""

import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FIXTURE = REPO / "docs" / "logging-examples.log"
BASH_LIB = REPO / "scripts" / "lib" / "log.sh"


def _load():
    loader = importlib.machinery.SourceFileLoader("jarvis_logs", str(HERE / "jarvis-logs"))
    spec = importlib.util.spec_from_loader("jarvis_logs", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jarvis_logs"] = mod  # dataclasses look the module up
    loader.exec_module(mod)
    return mod


jl = _load()
NOW = dt.datetime(2026, 9, 27, 16, 30, tzinfo=dt.UTC)


def line(ts, level, comp, logger, msg, turn="--------", attrs=""):
    return f"[{ts}] [{level:<5}] [{comp}] [{logger}] [{turn}] {msg}" + (
        f"  {attrs}" if attrs else ""
    )


class TmpDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, *lines, size=None):
        p = self.dir / name
        if size is not None:
            with open(p, "wb") as fh:
                fh.truncate(size)
        else:
            p.write_text("".join(ln + "\n" for ln in lines))
        return p

    def run_cli(self, *argv):
        out = io.StringIO()
        rc = jl.main(
            ["--dir", str(self.dir), *argv]
            if argv[:1] not in (["prune"], ["usage"])
            else [argv[0], "--dir", str(self.dir), *argv[1:]],
            now=NOW,
            out=out,
        )
        return rc, out.getvalue()


class ParseFixture(unittest.TestCase):
    """Every record of the shared fixture (docs/logging-examples.log)."""

    def setUp(self):
        self.recs = list(jl.parse(FIXTURE.read_text().splitlines()))

    def test_every_record_parses(self):
        n_starts = sum(1 for ln in FIXTURE.read_text().splitlines() if ln.startswith("["))
        self.assertEqual(len(self.recs), n_starts)
        for r in self.recs:
            self.assertRegex(r.ts, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}Z$")
            self.assertIn(r.level, jl.LEVELS)
            self.assertTrue(r.component and r.logger)
            self.assertRegex(r.turn, r"^([0-9a-f]{8}|-{8})$")
            self.assertEqual(r.lines[0], r.text.splitlines()[0])

    def test_lines_round_trip(self):
        self.assertEqual("\n".join(r.text for r in self.recs), FIXTURE.read_text().rstrip("\n"))

    def test_fields(self):
        by_msg = {r.message: r for r in self.recs}
        r = by_msg["log opened"]
        self.assertEqual((r.level, r.component, r.logger), ("INFO", "agent", "log"))
        self.assertEqual(r.attrs, {"service.version": "0.2.0", "pid": "1"})
        r = by_msg["turn started"]
        self.assertEqual(r.turn, "4bf92f35")
        self.assertEqual(r.attrs["trace_id"], "4bf92f3577b34da6a3ce929d0e0e4736")
        self.assertEqual(by_msg["heard text"].attrs, {"text": "what's the weather today?"})
        self.assertEqual(by_msg["slow first token, falling back"].level, "WARN")
        r = by_msg["reply ready\nsecond line kept on one line"]
        self.assertEqual(r.attrs, {"note": 'has "quotes" and a \\ backslash', "empty": ""})

    def test_continuation_lines_stay_with_their_record(self):
        err = next(r for r in self.recs if r.level == "ERROR")
        self.assertEqual(len(err.lines), 5)
        self.assertEqual(err.lines[1], "    at jarvis_agent/speech/tts.py:88 in synthesize")
        self.assertEqual(err.attrs, {"error.type": "TimeoutError"})
        fatal = next(r for r in self.recs if r.level == "FATAL")
        self.assertEqual((fatal.component, len(fatal.lines)), ("app", 2))
        self.assertEqual(fatal.attrs, {})

    def test_malformed_lines_are_kept(self):
        recs = list(
            jl.parse(
                [
                    "garbage first",
                    line("2026-09-27 10:00:00.000Z", "INFO", "a", "b", "m"),
                    "[not a record",
                ]
            )
        )
        self.assertEqual(len(recs), 2)
        self.assertIsNone(recs[0].level)
        self.assertEqual(recs[1].lines[1], "[not a record")

    def test_message_with_double_space_but_no_attrs(self):
        r = jl.parse_line(line("2026-09-27 10:00:00.000Z", "INFO", "a", "b", "two  spaces here"))
        self.assertEqual((r.message, r.attrs), ("two  spaces here", {}))


class BashWriter(unittest.TestCase):
    """scripts/lib/log.sh writes exactly the fixture's lines (bar the timestamp)."""

    def bash_log(self, rec, log_dir="/nonexistent"):
        args = [rec.level, rec.logger, rec.message, *(f"{k}={v}" for k, v in rec.attrs.items())]
        env = dict(
            os.environ,
            JARVIS_LOG_DIR=log_dir,
            JARVIS_LOG_COMPONENT=rec.component,
            JARVIS_LOG_TURN=rec.turn,
        )
        p = subprocess.run(
            ["bash", "-c", '. "$0"; log "$@"', str(BASH_LIB), *args],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return p.stderr.rstrip("\n")

    def test_every_single_line_fixture_record(self):
        recs = [r for r in jl.parse(FIXTURE.read_text().splitlines()) if len(r.lines) == 1]
        self.assertGreaterEqual(len(recs), 8)
        for r in recs:
            with self.subTest(r.message):
                got = self.bash_log(r)
                self.assertRegex(got, r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}Z\] ")
                self.assertEqual(got[26:], r.lines[0][26:])

    def test_writes_the_daily_file_0640(self):
        with tempfile.TemporaryDirectory() as d:
            r = jl.parse_line(line("2026-09-27 10:00:00.000Z", "WARN", "deploy", "rollback", "x"))
            self.bash_log(r, d)
            (f,) = Path(d).iterdir()
            self.assertRegex(f.name, r"^jarvis-deploy-\d{4}-\d\d-\d\d\.log$")
            self.assertEqual(oct(f.stat().st_mode & 0o777), "0o640")
            self.assertEqual(len(list(jl.parse(f.read_text().splitlines()))), 1)

    def test_never_follows_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "target"
            target.write_text("keep\n")
            today = dt.datetime.now(dt.UTC).date().isoformat()
            (Path(d) / f"jarvis-deploy-{today}.log").symlink_to(target)
            r = jl.parse_line(line("2026-09-27 10:00:00.000Z", "INFO", "deploy", "x", "hello"))
            self.assertIn("hello", self.bash_log(r, d))  # still on stderr
            self.assertEqual(target.read_text(), "keep\n")


class MergeAndFilter(TmpDir):
    def setUp(self):
        super().setUp()
        d1, d2 = "2026-09-26", "2026-09-27"
        self.write(
            f"jarvis-agent-{d1}.log",
            line(f"{d1} 23:59:59.000Z", "INFO", "agent", "voice.loop", "late agent"),
        )
        self.write(
            f"jarvis-app-{d2}.log",
            line(f"{d2} 15:00:00.100Z", "INFO", "app", "presence", "app 1", "4bf92f35"),
            line(f"{d2} 16:20:00.000Z", "DEBUG", "app", "ws", "app 2"),
        )
        self.write(
            f"jarvis-agent-{d2}.log",
            line(
                f"{d2} 15:00:00.000Z",
                "INFO",
                "agent",
                "voice.loop",
                "agent 1",
                "4bf92f35",
                "trace_id=4bf92f3577b34da6a3ce929d0e0e4736",
            ),
            line(f"{d2} 15:00:00.200Z", "ERROR", "agent", "tts", "agent 2", "4bf92f35"),
            "    at tts.py:1 in f",
            line(f"{d2} 16:25:00.000Z", "WARN", "agent", "routing", "agent 3"),
        )
        self.write(
            f"jarvis-deploy-{d2}.log",
            line(f"{d2} 15:00:00.150Z", "WARN", "deploy", "rollback", "deploy 1"),
        )
        self.write("notes.txt", "[2026-09-27 00:00:00.000Z] not a log file")

    def messages(self, *argv):
        rc, out = self.run_cli(*argv)
        self.assertEqual(rc, 0)
        return [r.message for r in jl.parse(out.splitlines())]

    def test_merge_order_across_components_and_days(self):
        self.assertEqual(
            self.messages(),
            ["late agent", "agent 1", "app 1", "deploy 1", "agent 2", "app 2", "agent 3"],
        )

    def test_continuation_follows_its_record(self):
        _, out = self.run_cli()
        lines = out.splitlines()
        self.assertEqual(
            lines[lines.index(next(x for x in lines if "agent 2" in x)) + 1], "    at tts.py:1 in f"
        )

    def test_turn(self):
        self.assertEqual(self.messages("--turn", "4bf92f35"), ["agent 1", "app 1", "agent 2"])
        self.assertEqual(
            self.messages("--turn", "4BF92F3577B34DA6A3CE929D0E0E4736"),
            ["agent 1", "app 1", "agent 2"],
        )
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_cli("--turn", "xyz")

    def test_level(self):
        self.assertEqual(self.messages("--level", "warn"), ["deploy 1", "agent 2", "agent 3"])
        self.assertEqual(self.messages("--level", "ERROR"), ["agent 2"])

    def test_component(self):
        self.assertEqual(self.messages("--component", "app"), ["app 1", "app 2"])
        self.assertEqual(
            self.messages("--component", "app", "--component", "deploy"),
            ["app 1", "deploy 1", "app 2"],
        )

    def test_since(self):
        self.assertEqual(self.messages("--since", "15m"), ["app 2", "agent 3"])
        self.assertEqual(self.messages("--since", "1h"), ["app 2", "agent 3"])
        self.assertEqual(len(self.messages("--since", "2d")), 7)
        self.assertEqual(
            self.messages("--since", "2026-09-27T15:00:00.150"),
            ["deploy 1", "agent 2", "app 2", "agent 3"],
        )
        self.assertEqual(
            self.messages("--since", "2026-09-27T17:00:00.150+02:00"),
            ["deploy 1", "agent 2", "app 2", "agent 3"],
        )
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_cli("--since", "yesterday")

    def test_combined_and_last_n(self):
        self.assertEqual(
            self.messages("--level", "INFO", "--component", "agent", "-n", "2"),
            ["agent 2", "agent 3"],
        )


class Follow(TmpDir):
    def test_new_lines_new_files_and_truncation(self):
        f = self.write(
            "jarvis-agent-2026-09-27.log",
            line("2026-09-27 10:00:00.000Z", "INFO", "agent", "a", "old"),
        )
        fol = jl.Follower(self.dir, jl.Filter(), start=jl.log_files(self.dir))
        self.assertEqual(fol.poll(), [])
        with open(f, "a") as fh:
            new = line("2026-09-27 10:00:01.000Z", "ERROR", "agent", "a", "new")
            fh.write(new + "\n    at x\n")
            fh.write("[2026-09-27 10:00:02.000Z] [INFO ] [agent] [a] [--------] parti")
        self.write(
            "jarvis-app-2026-09-27.log",
            line("2026-09-27 10:00:00.500Z", "INFO", "app", "p", "app new"),
        )
        recs = fol.poll()
        self.assertEqual([r.message for r in recs], ["app new", "new"])
        self.assertEqual(recs[1].lines[1], "    at x")
        with open(f, "a") as fh:
            fh.write("al\n")
        self.assertEqual([r.message for r in fol.poll()], ["partial"])
        f.write_text(line("2026-09-27 11:00:00.000Z", "INFO", "agent", "a", "rotated") + "\n")
        self.assertEqual([r.message for r in fol.poll()], ["rotated"])

    def test_filter_applies(self):
        fol = jl.Follower(self.dir, jl.Filter(min_level="WARN"))
        self.write(
            "jarvis-agent-2026-09-27.log",
            line("2026-09-27 10:00:00.000Z", "INFO", "agent", "a", "info"),
            line("2026-09-27 10:00:01.000Z", "WARN", "agent", "a", "warn"),
        )
        self.assertEqual([r.message for r in fol.poll()], ["warn"])


class Prune(TmpDir):
    def day(self, days_ago):
        return (NOW.date() - dt.timedelta(days=days_ago)).isoformat()

    def names(self):
        return sorted(p.name for p in self.dir.iterdir())

    def test_age_then_budget(self):
        for ago in (0, 1, 50, 89, 90, 200):
            self.write(f"jarvis-agent-{self.day(ago)}.log", size=100)
        self.write(f"jarvis-app-{self.day(89)}.log", size=100)
        self.write("jarvis-agent-2026-13-45.log", size=100)  # not a real date
        self.write(f"other-{self.day(200)}.log", size=100)
        self.write("jarvis-agent-2020-01-01.log.gz", size=100)
        keep_out = {
            "jarvis-agent-2026-13-45.log",
            f"other-{self.day(200)}.log",
            "jarvis-agent-2020-01-01.log.gz",
        }
        rc, out = self.run_cli("prune", "--budget", "300")
        self.assertEqual(rc, 0)
        left = set(self.names()) - keep_out
        # 90 and 200 days: too old. Then 5 files (500 B) > 300 B: the oldest two go.
        self.assertEqual(left, {f"jarvis-agent-{self.day(a)}.log" for a in (0, 1, 50)})
        self.assertTrue(keep_out <= set(self.names()))
        self.assertIn("older than 90 days", out)
        self.assertIn("over budget", out)

    def test_dry_run_deletes_nothing(self):
        self.write(f"jarvis-agent-{self.day(120)}.log", size=10)
        before = self.names()
        rc, out = self.run_cli("prune", "--dry-run")
        self.assertEqual((rc, self.names()), (0, before))
        self.assertIn("would delete jarvis-agent-", out)

    def test_flags(self):
        self.write(f"jarvis-agent-{self.day(8)}.log", size=10)
        self.write(f"jarvis-agent-{self.day(6)}.log", size=10)
        self.run_cli("prune", "--max-age-days", "7")
        self.assertEqual(self.names(), [f"jarvis-agent-{self.day(6)}.log"])

    def test_keeps_todays_files_and_symlinks(self):
        self.write(f"jarvis-agent-{self.day(0)}.log", size=1000)
        target = self.dir / "target"
        target.write_text("x")
        (self.dir / f"jarvis-agent-{self.day(300)}.log").symlink_to(target)
        rc, out = self.run_cli("prune", "--budget", "10")
        self.assertEqual(rc, 0)
        self.assertIn(f"jarvis-agent-{self.day(0)}.log", self.names())
        self.assertIn(f"jarvis-agent-{self.day(300)}.log", self.names())
        self.assertIn("still over budget", out)

    def test_sizes(self):
        self.assertEqual(jl.parse_size("20G"), 20 * 1024**3)
        self.assertEqual(jl.parse_size("500MiB"), 500 * 1024**2)
        self.assertEqual(jl.parse_size("1024"), 1024)


class Usage(TmpDir):
    def test_report(self):
        self.write("jarvis-agent-2026-08-31.log", size=1024**2)
        self.write("jarvis-agent-2026-09-01.log", size=2 * 1024**2)
        self.write("jarvis-app-2026-09-01.log", size=512 * 1024)
        self.write("jarvis-deploy-2026-09-27.log", size=10)
        self.write("unrelated.log", size=1024**3)
        rc, out = self.run_cli("usage", "--budget", "100M", "--daily-cap", "4M")
        self.assertEqual(rc, 0)
        self.assertIn("3.5 MiB of 100.0 MiB budget (3.5%)", out)
        rows = {ln.split()[0]: ln.split() for ln in out.splitlines() if ln[:4].isdigit()}
        head = next(ln for ln in out.splitlines() if ln.startswith("day")).split()
        self.assertEqual(head[:5], ["day", "agent", "app", "deploy", "total"])
        self.assertEqual(rows["2026-09-01"][-1], "50%")  # agent 2 MiB of a 4 MiB cap
        self.assertEqual(" ".join(rows["2026-09-01"][1:3]), "2.0 MiB")
        self.assertIn("2026-08", rows)
        self.assertEqual(" ".join(rows["2026-09"][-2:]), "2.5 MiB")
        self.assertNotIn("1.0 GiB", out)

    def test_empty(self):
        rc, out = self.run_cli("usage")
        self.assertEqual(rc, 0)
        self.assertIn("no log files", out)
        self.assertTrue(re.search(r"0 B of 20\.0 GiB budget \(0\.0%\)", out))


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(os.geteuid() == 0, "root can read any file")
class Unreadable(TmpDir):
    def test_says_why_it_skips_a_file_and_reads_the_rest(self):
        day = NOW.date().isoformat()
        ok = line(f"{day} 10:00:00.000Z", "INFO ", "agent", "runtime", "agent ready")
        self.write(f"jarvis-agent-{day}.log", ok)
        secret = self.write(f"jarvis-app-{day}.log", ok.replace("agent]", "app]"))
        secret.chmod(0)
        jl._warned.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc, out = self.run_cli("--since", "1d")
            self.run_cli("--since", "1d")  # warned once per file
        self.assertEqual(rc, 0)
        self.assertIn("agent ready", out)
        self.assertEqual(err.getvalue().count("can't read"), 1)
        self.assertIn(f"jarvis-app-{day}.log", err.getvalue())
        self.assertIn("jarvis-log group", err.getvalue())
