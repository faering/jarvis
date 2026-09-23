"""Tests for wi_text. Run: python3 -m unittest discover -s .claude/skills/_shared"""

import json
import tempfile
import unittest
from pathlib import Path

from wi_text import find_entities, normalize_body, normalize_item, normalize_mirror, normalize_title


class TitleTest(unittest.TestCase):
    def test_decodes_entities(self):
        self.assertEqual(
            normalize_title("Integration &amp; discovery (MCP tools + event bus)"),
            "Integration & discovery (MCP tools + event bus)",
        )
        self.assertEqual(normalize_title("event -&gt; speak now"), "event -> speak now")

    def test_decodes_double_escaping(self):
        self.assertEqual(normalize_title("A &amp;amp; B"), "A & B")

    def test_numeric_entities(self):
        self.assertEqual(normalize_title("it&#39;s &#x2192; done"), "it's → done")

    def test_plain_text_untouched(self):
        self.assertEqual(normalize_title("Add <thing> & stuff"), "Add <thing> & stuff")

    def test_inline_code_kept(self):
        self.assertEqual(normalize_title("Escape `&amp;` in X"), "Escape `&amp;` in X")


class BodyTest(unittest.TestCase):
    def test_decodes_prose(self):
        self.assertEqual(normalize_body("- [ ] a &amp; b -&gt; c"), "- [ ] a & b -> c")

    def test_code_untouched(self):
        body = "x &amp; y\n\n```html\n&lt;div&gt; &amp;\n```\n\nand `&gt;` inline"
        self.assertEqual(
            normalize_body(body), "x & y\n\n```html\n&lt;div&gt; &amp;\n```\n\nand `&gt;` inline"
        )

    def test_keeps_tag_openers_escaped(self):
        # Decoding to "<div>" would render as HTML, so "<" stays escaped before a tag.
        self.assertEqual(normalize_body("use &lt;div&gt; here"), "use &lt;div> here")
        self.assertEqual(normalize_body("a &lt; b"), "a < b")

    def test_crlf(self):
        self.assertEqual(normalize_body("a\r\nb\rc"), "a\nb\nc")

    def test_idempotent(self):
        once = normalize_body("a &amp;amp; &lt;b&gt; `&amp;`")
        self.assertEqual(normalize_body(once), once)


class CheckTest(unittest.TestCase):
    def test_finds_entities_outside_code(self):
        self.assertEqual(find_entities("a &amp; b `&gt;`"), ["&amp;"])

    def test_clean_text(self):
        self.assertEqual(find_entities("a & b; &lt;div>"), [])
        self.assertEqual(find_entities("R&D; fine"), [])


class MirrorTest(unittest.TestCase):
    def test_normalizes_items(self):
        item = {
            "title": "Trust &amp; allowlist",
            "summary": "x -&gt; y",
            "acceptanceCriteria": ["a &amp; b", "`&amp;`"],
            "archDecisions": None,
        }
        self.assertEqual(
            normalize_item(item),
            {
                "title": "Trust & allowlist",
                "summary": "x -> y",
                "acceptanceCriteria": ["a & b", "`&amp;`"],
                "archDecisions": None,
            },
        )

    def test_mirror_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "github-issues.json"
            path.write_text(json.dumps({"items": [{"title": "A &amp; B"}, {"title": "C"}]}))
            self.assertEqual(normalize_mirror(path), 1)
            self.assertEqual(json.loads(path.read_text())["items"][0]["title"], "A & B")


if __name__ == "__main__":
    unittest.main()
