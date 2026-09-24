import pytest
from fastapi.testclient import TestClient

from jarvis_agent import __version__
from jarvis_agent.main import app
from jarvis_agent.version import build_info

SHA = "0123456789abcdef0123456789abcdef01234567"
ENV_VARS = ("JARVIS_VERSION", "JARVIS_REVISION", "JARVIS_BUILD_TIME")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return TestClient(app)


def _inject(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    monkeypatch.setenv("JARVIS_VERSION", version)
    monkeypatch.setenv("JARVIS_REVISION", SHA)
    monkeypatch.setenv("JARVIS_BUILD_TIME", "2026-09-24T12:00:00Z")


@pytest.mark.parametrize(
    ("version", "dirty"),
    [
        ("1.2.3", False),
        ("1.2.3+4.g0123456", False),
        ("1.2.3+4.g0123456.dirty", True),
    ],
)
def test_version_endpoint_reports_injected_build(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, version: str, dirty: bool
) -> None:
    _inject(monkeypatch, version)
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {
        "version": version,
        "revision": SHA,
        "dirty": dirty,
        "build_time": "2026-09-24T12:00:00Z",
    }


def test_version_endpoint_falls_back_without_build_args(client: TestClient) -> None:
    assert client.get("/version").json() == {
        "version": __version__,
        "revision": "unknown",
        "dirty": False,
        "build_time": None,
    }


def test_empty_values_count_as_unset() -> None:
    # docker compose passes unset build args through as empty strings.
    assert build_info({name: "" for name in ENV_VARS}) == build_info({})


def test_hello_carries_the_canonical_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject(monkeypatch, "1.2.3+4.g0123456.dirty")
    with client.websocket_connect("/ws") as session:
        assert session.receive_json()["payload"]["agent"] == "1.2.3+4.g0123456.dirty"
