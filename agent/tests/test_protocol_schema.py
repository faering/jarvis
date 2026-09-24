"""The Python protocol must match packages/protocol/protocol.schema.json (the source of truth).

The schema is read from the repo checkout, so these tests run in the devcontainer/CI, not
inside the agent image. Adding a message type: see the schema's top-level description.
"""

import ast
import json
from pathlib import Path
from typing import Any

import pytest

import jarvis_agent
from jarvis_agent import protocol
from jarvis_agent.protocol import PROTOCOL_VERSION, Envelope

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "packages/protocol/protocol.schema.json"
SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
DEFS: dict[str, Any] = SCHEMA["$defs"]

_JSON_TYPES = {str: "string", int: "integer", bool: "boolean", float: "number"}


def _types(prop: dict[str, Any]) -> set[str]:
    """JSON types a property allows, from either `type` or pydantic's `anyOf`."""
    if "anyOf" in prop:
        return set().union(*(_types(p) for p in prop["anyOf"]))
    kind = prop["type"]
    return set(kind) if isinstance(kind, list) else {kind}


def _conforms(payload: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Tiny structural check (required keys + property types) — no validator dependency."""
    if any(key not in payload for key in schema["required"]):
        return False
    return all(
        _JSON_TYPES.get(type(payload[key])) in _types(prop)
        for key, prop in schema["properties"].items()
        if key in payload
    )


def _called_name(call: ast.Call) -> str | None:
    """`Envelope(...)` and `protocol.Envelope(...)` both give "Envelope"."""
    func = call.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)


def _agent_message_types() -> set[str]:
    """Message types the agent builds (`Envelope(type="...")`) or dispatches on (`.type`)."""
    found: set[str] = set()
    for path in Path(jarvis_agent.__file__).parent.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and _called_name(node) == "Envelope":
                found |= {
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "type" and isinstance(kw.value, ast.Constant)
                }
            elif isinstance(node, ast.Match) and getattr(node.subject, "attr", None) == "type":
                found |= {
                    case.pattern.value.value
                    for case in node.cases
                    if isinstance(case.pattern, ast.MatchValue)
                    and isinstance(case.pattern.value, ast.Constant)
                }
            elif isinstance(node, ast.Compare) and getattr(node.left, "attr", None) == "type":
                found |= {c.value for c in node.comparators if isinstance(c, ast.Constant)}
    return found


def test_protocol_version_matches() -> None:
    assert SCHEMA["properties"]["v"]["const"] == PROTOCOL_VERSION


def test_envelope_shape_matches() -> None:
    model = Envelope.model_json_schema()
    assert model["properties"].keys() == SCHEMA["properties"].keys()
    assert set(model["required"]) == set(SCHEMA["required"])
    assert model["additionalProperties"] is SCHEMA["additionalProperties"] is False
    for name, prop in SCHEMA["properties"].items():
        mine = model["properties"][name]
        assert _types(mine) == _types(prop), name
        assert mine.get("minLength") == prop.get("minLength"), name
        if "default" in prop:
            default = Envelope.model_fields[name].get_default(call_default_factory=True)
            assert default == prop["default"], name


def test_schema_routes_every_message_type() -> None:
    routed = {rule["if"]["properties"]["type"]["const"]: rule["then"] for rule in SCHEMA["allOf"]}
    assert routed.keys() == DEFS.keys()
    for kind, then in routed.items():
        assert then["properties"]["payload"]["$ref"] == f"#/$defs/{kind}"


def test_agent_message_types_are_in_schema() -> None:
    """A type the agent sends or handles must be in the schema (and vice versa)."""
    assert _agent_message_types() == DEFS.keys()


@pytest.mark.parametrize(
    ("kind", "example"), [(kind, ex) for kind, d in DEFS.items() for ex in d["examples"]]
)
def test_schema_examples_are_valid_envelopes(kind: str, example: dict[str, Any]) -> None:
    assert _conforms(example, DEFS[kind])
    Envelope.model_validate({"v": PROTOCOL_VERSION, "type": kind, "payload": example})


@pytest.mark.parametrize(
    "frame",
    [
        protocol.hello("1.2.3"),
        protocol.pong(Envelope(v=PROTOCOL_VERSION, type="ping", id="p-1")),
        protocol.error("bad_json", "frame is not valid JSON", "r-1"),
    ],
    ids=lambda frame: frame.type,
)
def test_agent_frames_match_schema(frame: Envelope) -> None:
    assert _conforms(frame.payload, DEFS[frame.type])
    assert frame.model_dump().keys() == SCHEMA["properties"].keys()
