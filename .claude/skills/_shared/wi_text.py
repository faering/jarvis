#!/usr/bin/env python3
"""Normalize work-item text at the mirror <-> GitHub boundary.

GitHub stores issue titles as plain text and bodies as raw Markdown. Any HTML entity we
send (``&amp;``, ``-&gt;``) is stored verbatim, and titles then show it literally. This
helper decodes entities so the mirror and GitHub only ever carry raw text.

Rules:
- Entities are decoded repeatedly, so double-escaped text (``&amp;amp;``) is fixed too.
- Markdown code (fenced blocks and inline code spans) is left untouched: entities there
  are literal and meant to be shown as typed.
- In Markdown bodies a decoded ``<`` that would open an HTML tag is kept as ``&lt;``, so
  the rendered output does not change.
- Line endings are normalized to ``\\n`` (the web UI saves ``\\r\\n``), which keeps
  baseSnapshot hashes stable.

CLI (stdlib only):
    wi_text.py title  < text        # normalize a title (plain text)
    wi_text.py body   < text        # normalize a Markdown body
    wi_text.py check  < text        # exit 1 and list entities found outside code
    wi_text.py mirror [PATH]        # normalize github-issues.json in place
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

_MAX_PASSES = 5
_ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9A-Fa-f]+);")
_FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,}).*?^\1\2[ \t]*$", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"(`+)(?!`).+?(?<!`)\1", re.DOTALL)
_TAG_START = re.compile(r"<(?=[A-Za-z/!?])")

# Mirror fields holding Markdown fragments (title is handled as plain text).
_MARKDOWN_FIELDS = ("summary", "acceptanceCriteria", "archDecisions")


def _unescape(text: str) -> str:
    for _ in range(_MAX_PASSES):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _split_code(text: str) -> list[tuple[bool, str]]:
    """Split Markdown into (is_code, chunk) pieces: fenced blocks, inline code, prose."""
    pieces: list[tuple[bool, str]] = []
    pos = 0
    for fence in _FENCE.finditer(text):
        pieces.extend(_split_inline(text[pos : fence.start()]))
        pieces.append((True, fence.group(0)))
        pos = fence.end()
    pieces.extend(_split_inline(text[pos:]))
    return pieces


def _split_inline(text: str) -> list[tuple[bool, str]]:
    pieces: list[tuple[bool, str]] = []
    pos = 0
    for span in _INLINE_CODE.finditer(text):
        pieces.append((False, text[pos : span.start()]))
        pieces.append((True, span.group(0)))
        pos = span.end()
    pieces.append((False, text[pos:]))
    return [p for p in pieces if p[1]]


def _normalize(text: str, *, markdown: bool) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for is_code, chunk in _split_code(text):
        if not is_code:
            chunk = _unescape(chunk)
            if markdown:
                chunk = _TAG_START.sub("&lt;", chunk)
        out.append(chunk)
    return "".join(out)


def normalize_title(text: str) -> str:
    """Normalize a plain-text title (inline code spans are kept as typed)."""
    return _normalize(text, markdown=False).strip()


def normalize_body(text: str) -> str:
    """Normalize a Markdown body or fragment without changing how it renders."""
    return _normalize(text, markdown=True)


def find_entities(text: str, *, markdown: bool = True) -> list[str]:
    """Return entities found outside code that normalization would decode."""
    found = []
    for is_code, chunk in _split_code(text):
        if not is_code:
            found += [m for m in _ENTITY.findall(chunk) if html.unescape(m) != m]
    if markdown:
        found = [m for m in found if m != "&lt;"]
    return found


def normalize_item(item: dict) -> dict:
    """Normalize one mirror WorkItem's text fields in place and return it."""
    if isinstance(item.get("title"), str):
        item["title"] = normalize_title(item["title"])
    for field in _MARKDOWN_FIELDS:
        value = item.get(field)
        if isinstance(value, str):
            item[field] = normalize_body(value)
        elif isinstance(value, list):
            item[field] = [normalize_body(v) if isinstance(v, str) else v for v in value]
    return item


def normalize_mirror(path: Path) -> int:
    """Normalize every item in the mirror file; return how many items changed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for item in data.get("items", []):
        before = json.dumps(item, sort_keys=True)
        normalize_item(item)
        changed += json.dumps(item, sort_keys=True) != before
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "title":
        sys.stdout.write(normalize_title(sys.stdin.read()))
    elif cmd == "body":
        sys.stdout.write(normalize_body(sys.stdin.read()))
    elif cmd == "check":
        found = find_entities(sys.stdin.read())
        if found:
            print("HTML entities found:", " ".join(sorted(set(found))), file=sys.stderr)
            return 1
    elif cmd == "mirror":
        path = Path(argv[2] if len(argv) > 2 else "github-issues.json")
        print(f"normalized {normalize_mirror(path)} item(s) in {path}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
