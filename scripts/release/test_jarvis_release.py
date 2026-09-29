"""Tests for scripts/release/jarvis-release (stdlib only, no network: `gh` is faked).

Run: python3 -m unittest discover -s scripts/release
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
FIXTURES = json.loads((HERE / "fixtures" / "github.json").read_text(encoding="utf-8"))


def _load():
    loader = importlib.machinery.SourceFileLoader("jarvis_release", str(HERE / "jarvis-release"))
    spec = importlib.util.spec_from_loader("jarvis_release", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jarvis_release"] = mod  # dataclasses look the module up
    loader.exec_module(mod)
    return mod


jr = _load()

README = """# Jarvis

## Roadmap

<!-- roadmap:start -->
old
<!-- roadmap:end -->

## Next
"""

MANIFEST = """number = 1
version = "1.0"
codename = "Captain America"
milestone = "Jarvis 1: Lives on the Pi"

[components]
agent = "0.4.0"
app = "0.1.1"
"""


def fake_gh(*args):
    """The gh calls jarvis-release makes, answered from fixtures/github.json."""
    if args[:2] == ("release", "download"):
        return json.dumps(FIXTURES[f"release download {args[2]}"])
    path = next(a for a in args if a.startswith("repos/")).split("?")[0]
    items = FIXTURES[path]
    if path.endswith("/issues"):
        items = [i for i in items if "milestone=1" in " ".join(args)]
    return "".join(json.dumps(i) + "\n" for i in items)


# A git hook (pre-push) runs these tests with GIT_DIR etc. set for the real repo; neither
# the scratch repo nor the tool under test may inherit them, or git acts on the real repo.
for _var in [k for k in os.environ if k.startswith("GIT_")]:
    del os.environ[_var]
CLEAN_ENV = dict(os.environ)


def git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=CLEAN_ENV
    )


class RepoCase(unittest.TestCase):
    """A scratch git repo with a README, as ROOT; gh answers from fixtures."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        patches = [
            mock.patch.dict(os.environ, {**env, "JARVIS_REPO": "faering/jarvis"}),
            mock.patch.object(jr, "ROOT", self.root),
            mock.patch.object(jr, "gh", side_effect=fake_gh),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        git(self.root, "config", "commit.gpgsign", "false")
        git(self.root, "config", "tag.gpgsign", "false")
        (self.root / "README.md").write_text(README, encoding="utf-8")
        (self.root / "releases").mkdir()

    def commit_and_tag(self, tag):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", f"release {tag}")
        git(self.root, "tag", tag)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = jr.main(list(argv))
        return code, out.getvalue(), err.getvalue()


class ManifestTest(unittest.TestCase):
    def test_parse_and_dump_round_trip(self):
        m = jr.parse_manifest(MANIFEST)
        self.assertEqual((m.number, m.version, m.agent, m.app), (1, "1.0", "0.4.0", "0.1.1"))
        self.assertEqual(jr.parse_manifest(m.dumps()), m)
        self.assertEqual(m.tag, "jarvis-v1.0")
        self.assertEqual(m.title, "Jarvis 1 — Captain America")

    def test_minor_release_title_shows_the_version(self):
        m = jr.parse_manifest(MANIFEST.replace('"1.0"', '"1.1"'))
        self.assertEqual(m.title, "Jarvis 1.1 — Captain America")

    def test_invalid_manifest_lists_every_problem(self):
        bad = MANIFEST.replace('"1.0"', '"2.0"').replace('"0.4.0"', '"latest"')
        bad = bad.replace("Jarvis 1:", "Jarvis 3:")
        with self.assertRaises(jr.Error) as e:
            jr.parse_manifest(bad)
        msg = str(e.exception)
        self.assertIn("does not start with number 1", msg)
        self.assertIn("components.agent", msg)
        self.assertIn('"Jarvis 1: <outcome>"', msg)

    def test_invalid_toml(self):
        with self.assertRaises(jr.Error):
            jr.parse_manifest("number = ")

    def test_next_version(self):
        tags = ["jarvis-v1.0", "jarvis-v1.1", "jarvis-v2.0", "jarvis-vx"]
        self.assertEqual(jr.next_version(1, tags), "1.2")
        self.assertEqual(jr.next_version(2, tags), "2.1")
        self.assertEqual(jr.next_version(3, tags), "3.0")


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.ms = FIXTURES["repos/faering/jarvis/milestones"][0]
        self.issues = [
            i for i in FIXTURES["repos/faering/jarvis/issues"] if "pull_request" not in i
        ]
        self.man = jr.parse_manifest(MANIFEST)

    def test_sections_from_labels(self):
        notes = jr.render_notes(self.man, self.ms, self.issues)
        added = notes.split("## Added")[1].split("##")[0]
        self.assertIn("#37", added)
        self.assertIn("#158", added)  # stories are Added too
        self.assertIn("#140", notes.split("## Changed")[1].split("##")[0])
        self.assertIn("#141", notes.split("## Deprecated")[1].split("##")[0])
        self.assertIn("#185", notes.split("## Fixed")[1])
        self.assertNotIn("#145", notes)  # tasks aren't listed
        self.assertNotIn("#150", notes)  # not planned
        self.assertNotIn("#162", notes)  # still open
        order = [notes.index(f"## {s}") for s in jr.SECTIONS]
        self.assertEqual(order, sorted(order))

    def test_header_components_and_changelogs(self):
        notes = jr.render_notes(self.man, self.ms, self.issues)
        self.assertTrue(notes.startswith("**Jarvis 1 — Captain America**: Lives on the Pi"))
        self.assertIn("Jarvis runs on the Pi from a CI deploy.", notes)
        self.assertNotIn("Codename:", notes)
        self.assertIn(
            "https://github.com/faering/jarvis/blob/agent-v0.4.0/agent/CHANGELOG.md", notes
        )
        self.assertIn(
            "https://github.com/faering/jarvis/blob/app-v0.1.1/frontend/CHANGELOG.md", notes
        )
        self.assertIn("https://github.com/faering/jarvis/releases/tag/app-v0.1.1", notes)

    def test_previous_versions_shown(self):
        prev = jr.parse_manifest(MANIFEST.replace('"0.4.0"', '"0.3.0"'))
        notes = jr.render_notes(self.man, self.ms, self.issues, prev)
        self.assertIn("0.4.0 (was 0.3.0)", notes)
        self.assertNotIn("0.1.1 (was", notes)

    def test_notes_never_contain_closing_keywords(self):
        notes = jr.render_notes(self.man, self.ms, self.issues)
        self.assertEqual(jr.closing_keywords(notes), [])
        self.assertIn("fixes issue #12", notes)

    def test_closing_keyword_detection(self):
        for text in (
            "Closes #1",
            "fixed: #2",
            "Resolves faering/jarvis#3",
            "fix https://github.com/faering/jarvis/issues/4",
        ):
            self.assertTrue(jr.closing_keywords(text), text)
            self.assertFalse(jr.closing_keywords(jr.defuse(text)), text)
        for text in ("Refs #1", "#2 fixed", "prefix #3", "Fixes the bug"):
            self.assertFalse(jr.closing_keywords(text), text)

    def test_codename_from_milestone(self):
        self.assertEqual(jr.milestone_codename(self.ms["description"]), "Captain America")
        other = FIXTURES["repos/faering/jarvis/milestones"][1]["description"]
        self.assertIsNone(jr.milestone_codename(other))
        self.assertIsNone(jr.milestone_codename(None))


class ReadmeTest(unittest.TestCase):
    def test_block_from_milestones_and_manifests(self):
        mss = FIXTURES["repos/faering/jarvis/milestones"]
        block = jr.roadmap_block(mss, [jr.parse_manifest(MANIFEST)])
        self.assertTrue(block.startswith(jr.START) and block.endswith(jr.END))
        self.assertIn(
            "Jarvis 1 - Captain America : Lives on the Pi : released as jarvis-v1.0", block
        )
        self.assertIn("Jarvis 2 - TBD : Ears and mouth : due 2026-11-15", block)
        self.assertNotIn("Someday", block)

    def test_replace_block_keeps_the_rest(self):
        out = jr.replace_block(README, f"{jr.START}\nnew\n{jr.END}")
        self.assertIn("new", out)
        self.assertNotIn("old", out)
        self.assertTrue(out.endswith("## Next\n"))

    def test_missing_block(self):
        with self.assertRaises(jr.Error):
            jr.replace_block("# no block\n", "x")


class DraftTest(RepoCase):
    def test_draft_writes_manifest_notes_and_readme(self):
        code, out, _ = self.run_cli(
            "draft", "--milestone", "Jarvis 1: Lives on the Pi", "--codename", "Captain America"
        )
        self.assertEqual(code, 0)
        man = jr.load_manifest(self.root / "releases" / "jarvis-1.toml")
        # Latest *complete* releases: agent-v0.10.0 is a draft, app-v0.1.2 lacks manifest.json.
        self.assertEqual((man.version, man.agent, man.app), ("1.0", "0.4.0", "0.1.1"))
        self.assertIn("## Added", (self.root / "releases" / "jarvis-1.md").read_text())
        self.assertIn("released as jarvis-v1.0", (self.root / "README.md").read_text())
        self.assertIn("warning: #162 is still open", out)

    def test_draft_codename_defaults_to_the_milestone(self):
        code, _, _ = self.run_cli("draft", "--milestone", "Jarvis 1: Lives on the Pi")
        self.assertEqual(code, 0)
        self.assertEqual(
            jr.load_manifest(self.root / "releases/jarvis-1.toml").codename, "Captain America"
        )

    def test_draft_refuses_unpublished_versions(self):
        code, _, err = self.run_cli(
            "draft", "--milestone", "Jarvis 1: Lives on the Pi", "--app", "0.1.2"
        )
        self.assertEqual(code, 1)
        self.assertIn("app-v0.1.2 is not a complete published release", err)

    def test_second_set_is_minor_with_the_same_codename(self):
        self.run_cli("draft", "--milestone", "Jarvis 1: Lives on the Pi")
        self.commit_and_tag("jarvis-v1.0")
        code, _, err = self.run_cli(
            "draft", "--milestone", "Jarvis 1: Lives on the Pi", "--codename", "Iron Man"
        )
        self.assertEqual(code, 1)
        self.assertIn("one codename per number", err)
        code, _, _ = self.run_cli(
            "draft", "--milestone", "Jarvis 1: Lives on the Pi", "--agent", "0.3.0"
        )
        self.assertEqual(code, 0)
        man = jr.load_manifest(self.root / "releases/jarvis-1.toml")
        self.assertEqual((man.version, man.codename), ("1.1", "Captain America"))
        self.assertIn("0.3.0 (was 0.4.0)", (self.root / "releases/jarvis-1.md").read_text())


class CheckTest(RepoCase):
    def write(self, manifest=MANIFEST, notes="Clean notes, see #12.\n", name="jarvis-1"):
        path = self.root / "releases" / f"{name}.toml"
        path.write_text(manifest, encoding="utf-8")
        if notes is not None:
            path.with_suffix(".md").write_text(notes, encoding="utf-8")
        return path

    def test_check_prints_env_for_ci(self):
        code, out, err = self.run_cli("check", str(self.write()), "--published")
        self.assertEqual(code, 0, err)
        env = dict(line.split("=", 1) for line in out.splitlines())
        self.assertEqual(env["TAG"], "jarvis-v1.0")
        self.assertEqual(env["TITLE"], "Jarvis 1 — Captain America")
        self.assertEqual((env["AGENT"], env["APP"]), ("0.4.0", "0.1.1"))
        self.assertEqual((env["AGENT_PROTOCOL"], env["APP_PROTOCOL"]), ("2", "2"))
        self.assertIn("::warning::#162 is still open", err)

    def test_check_refuses_closing_keywords_in_notes(self):
        code, _, err = self.run_cli("check", str(self.write(notes="Fixes #12\n")))
        self.assertEqual(code, 1)
        self.assertIn("closing keywords", err)

    def test_check_refuses_missing_notes_and_wrong_name(self):
        code, _, err = self.run_cli("check", str(self.write(notes=None)))
        self.assertEqual(code, 1)
        self.assertIn("missing notes", err)
        code, _, err = self.run_cli("check", str(self.write(name="jarvis-7")))
        self.assertEqual(code, 1)
        self.assertIn("must be named jarvis-1.toml", err)

    def test_check_refuses_existing_or_skipped_tag(self):
        path = self.write()
        self.commit_and_tag("jarvis-v1.0")
        code, _, err = self.run_cli("check", str(path))
        self.assertEqual(code, 1)
        self.assertIn("jarvis-v1.0 already exists", err)
        self.write(MANIFEST.replace('"1.0"', '"1.2"'))
        code, _, err = self.run_cli("check", str(path))
        self.assertEqual(code, 1)
        self.assertIn("the next is 1.1", err)

    def test_check_keeps_the_codename_per_number(self):
        path = self.write()
        self.commit_and_tag("jarvis-v1.0")
        self.write(MANIFEST.replace('"1.0"', '"1.1"').replace("Captain America", "Thor"))
        code, _, err = self.run_cli("check", str(path))
        self.assertEqual(code, 1)
        self.assertIn("one codename per number", err)

    def test_check_refuses_a_reused_codename(self):
        self.write()
        two = MANIFEST.replace("number = 1", "number = 2").replace('"1.0"', '"2.0"')
        two = two.replace("Jarvis 1:", "Jarvis 2:")
        code, _, err = self.run_cli("check", str(self.write(two, name="jarvis-2")))
        self.assertEqual(code, 1)
        self.assertIn("already Jarvis 1's", err)

    def test_check_published_refuses_incomplete_releases(self):
        path = self.write(MANIFEST.replace('"0.1.1"', '"0.1.2"'))
        code, _, err = self.run_cli("check", str(path), "--published")
        self.assertEqual(code, 1)
        self.assertIn("app-v0.1.2 is not a complete published release", err)

    def test_pending_lists_untagged_manifests(self):
        self.write()
        code, out, _ = self.run_cli("pending")
        self.assertEqual((code, out), (0, "releases/jarvis-1.toml\n"))
        self.commit_and_tag("jarvis-v1.0")
        self.assertEqual(self.run_cli("pending"), (0, "", ""))

    def test_readme_check_detects_drift(self):
        code, _, err = self.run_cli("readme", "--check")
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        self.assertEqual(self.run_cli("readme")[0], 0)
        self.assertEqual(self.run_cli("readme", "--check")[0], 0)


if __name__ == "__main__":
    unittest.main()
