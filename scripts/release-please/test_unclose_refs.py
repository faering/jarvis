"""Tests for unclose_refs.py (stdlib only).

Run: python3 -m unittest discover -s scripts/release-please
"""

import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from unclose_refs import unclose  # noqa: E402

URL = "https://github.com/faering/jarvis/issues"


class UncloseTest(unittest.TestCase):
    def test_release_please_line(self) -> None:
        line = f"* **agent:** x ([494e80b](https://x/commit/494e80b)), closes [#159]({URL}/159)"
        self.assertEqual(unclose(line), line.replace(", closes [#159]", ", refs [#159]"))

    def test_multiple_references(self) -> None:
        line = f"closes [#73]({URL}/73) [#72]({URL}/72)"
        self.assertEqual(unclose(line), f"refs [#73]({URL}/73) [#72]({URL}/72)")

    def test_every_keyword_and_form(self) -> None:
        keywords = ["close", "closes", "closed", "fix", "fixes", "fixed"]
        keywords += ["resolve", "resolves", "resolved"]
        refs = ["#1", "[#1](u)", "faering/jarvis#1", f"{URL}/1"]
        for kw in keywords + [k.upper() for k in keywords]:
            for ref in refs:
                for sep in (" ", ": ", ":"):
                    text = f"a {kw}{sep}{ref} b"
                    out = unclose(text)
                    self.assertNotIn(kw, out, text)
                    self.assertIn(f"{sep}{ref}", out, text)

    def test_capitalised_keyword_keeps_capital(self) -> None:
        self.assertEqual(unclose("Closes #3, closes #4"), "Refs #3, refs #4")

    def test_leaves_prose_alone(self) -> None:
        for text in (
            "### Bug Fixes",
            "fix the parser so it closes the socket",
            "prefixes #3 hotfix #4",
            "refs [#159](u)",
            "closes nothing here (#12 is just a mention)",
        ):
            self.assertEqual(unclose(text), text)

    def test_idempotent(self) -> None:
        once = unclose(f"x, closes [#1]({URL}/1), Fixes: #2")
        self.assertEqual(unclose(once), once)

    def test_real_agent_0_4_0_release_pr_body(self) -> None:
        body = (HERE / "fixture_pr182_body.md").read_text()
        out = unclose(body)
        self.assertIn(", refs [#159](", out)
        self.assertNotRegex(out.lower(), r"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b:?\s*\[?#")
        self.assertEqual(out, body.replace(", closes [#159](", ", refs [#159]("))

    def test_cli(self) -> None:
        run = subprocess.run(
            [sys.executable, str(HERE / "unclose_refs.py")],
            input="x, closes #7\n",
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(run.stdout, "x, refs #7\n")


if __name__ == "__main__":
    unittest.main()
