#!/usr/bin/env python3
"""Turn GitHub closing keywords in a release PR body into plain "refs" (#185).

release-please (<17.10.4, bundled by release-please-action@v5) renders every commit
footer reference as ", closes #n" - also `Refs #n`. GitHub acts on closing keywords in a
PR description merged into the default branch, so merging the release PR closed issues
that commits only referenced. Issues a commit really closed were already closed when that
commit's PR merged, so the release PR never needs to close anything: every
"<keyword> <issue>" becomes "refs <issue>". Idempotent; stdlib only.

Usage: unclose_refs.py < body.md > fixed.md
"""

import re
import sys

# GitHub's closing keywords, optionally followed by a colon, then an issue reference:
# #n, [#n](url), owner/repo#n, or an issue URL.
_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b"
    r"(?=:?\s*(?:\[?(?:[\w.-]+/[\w.-]+)?#\d+|https?://github\.com/[\w.-]+/[\w.-]+/issues/\d+))",
    re.IGNORECASE,
)


def _refs(match: re.Match[str]) -> str:
    return "Refs" if match.group(0)[0].isupper() else "refs"


def unclose(text: str) -> str:
    """Return ``text`` with every closing keyword before an issue reference as "refs"."""
    return _CLOSING.sub(_refs, text)


if __name__ == "__main__":
    sys.stdout.write(unclose(sys.stdin.read()))
