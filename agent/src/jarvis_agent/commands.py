"""App commands: what the agent may ask the app to do (ADR 0013).

The agent decides and the app executes; the names are the schema's closed list
(``$defs.command``), and the app ignores any it doesn't know.

INITIAL APPROACH, to revisit (#223): a request is recognised by fixed phrases, matched on
the whole utterance before the model runs. Ideally the model decides through tool calling,
but the on-device model (1.5B on the CPU; the Hailo NPU isn't in use yet) can't be trusted
with that. Only the wordings below work, in English.
"""

import re
from enum import StrEnum


class AppCommand(StrEnum):
    WINDOW_MINIMIZE = "window.minimize"


# The whole utterance, after normalize(), must be one of these.
PHRASES: dict[AppCommand, frozenset[str]] = {
    AppCommand.WINDOW_MINIMIZE: frozenset(
        {
            "minimize",
            "minimise",
            "minimize yourself",
            "minimise yourself",
            "minimize the window",
            "minimise the window",
            "minimize the app",
            "minimise the app",
            "hide",
            "hide yourself",
            "show me the desktop",
            "show the desktop",
            "go to the desktop",
        }
    ),
}

# What Jarvis says (and shows) when it runs the command.
REPLIES: dict[AppCommand, str] = {AppCommand.WINDOW_MINIMIZE: "Minimizing."}

# Politeness around a command: "Jarvis, could you minimize, please?"
_LEADING = ("hey", "ok", "okay", "jarvis", "please", "can", "could", "would", "will", "you")
_TRAILING = ("please", "now", "jarvis", "thanks", "thank you")


def normalize(text: str) -> str:
    """Lowercase words only, without the politeness around them."""
    words = re.sub(r"[^a-z]+", " ", text.lower()).split()
    while words and words[0] in _LEADING:
        words.pop(0)
    changed = True
    while changed:
        changed = False
        for tail in _TRAILING:
            n = len(tail.split())
            if len(words) > n and words[-n:] == tail.split():
                del words[-n:]
                changed = True
    return " ".join(words)


def match(text: str) -> AppCommand | None:
    """The command ``text`` asks for, if it is one of the fixed phrases."""
    phrase = normalize(text)
    for command, phrases in PHRASES.items():
        if phrase in phrases:
            return command
    return None
