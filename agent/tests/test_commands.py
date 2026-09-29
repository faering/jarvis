"""Fixed-phrase app commands (ADR 0013; an initial approach until the model decides, #223)."""

import json
from pathlib import Path

import pytest

from jarvis_agent.commands import PHRASES, REPLIES, AppCommand, match

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "packages/protocol/protocol.schema.json"


def test_commands_are_the_schemas_closed_list() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    names = schema["$defs"]["command"]["properties"]["name"]["enum"]
    assert {c.value for c in AppCommand} == set(names)
    assert PHRASES.keys() == REPLIES.keys() == set(AppCommand)


@pytest.mark.parametrize(
    "text",
    [
        "minimize",
        "Minimize.",
        "MINIMISE!",
        "Minimize yourself",
        "Jarvis, minimize.",
        "Hey Jarvis, could you minimize, please?",
        "Can you hide?",
        "hide yourself now",
        "Show me the desktop",
        "go to the desktop, thanks",
        "  minimize the window  ",
    ],
)
def test_minimize_phrases(text: str) -> None:
    assert match(text) is AppCommand.WINDOW_MINIMIZE


@pytest.mark.parametrize(
    "text",
    [
        "",
        "how do I minimize risk in my 3D prints?",
        "minimize the number of meetings tomorrow",
        "don't minimize",
        "where can I hide the cables",
        "what's on the desktop",
        "please",
        "Jarvis",
    ],
)
def test_other_utterances_are_not_commands(text: str) -> None:
    assert match(text) is None
