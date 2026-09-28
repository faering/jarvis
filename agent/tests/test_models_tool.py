"""The model playground (`python -m jarvis_agent.models`), against fake runtimes."""

import asyncio
import contextlib
import io
import json

import httpx
import pytest

from jarvis_agent.models.__main__ import main
from jarvis_agent.models.probe import chat, ollama_root

OLLAMA_ENV = {"JARVIS_RUNTIME_OLLAMA_URL": "http://ollama:11434/v1"}


def ollama(pulled: set[str] | None = None, requests: list | None = None) -> httpx.MockTransport:
    """A fake Ollama: streams 'Hello there!' in three chunks with exact stats."""
    pulled = {"qwen2.5:1.5b"} if pulled is None else pulled

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if requests is not None:
            requests.append((request.url.path, body))
        if request.url.path == "/api/chat":
            if body["model"] not in pulled:
                return httpx.Response(404, json={"error": f"model '{body['model']}' not found"})
            lines = [
                {"message": {"content": "Hello"}, "done": False},
                {"message": {"content": " there"}, "done": False},
                {"message": {"content": "!"}, "done": False},
                {
                    "message": {"content": ""},
                    "done": True,
                    "eval_count": 30,
                    "eval_duration": 2_000_000_000,
                    "load_duration": 1_500_000_000,
                },
            ]
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        if request.url.path == "/api/pull":
            lines = [
                {"status": "pulling manifest"},
                {"status": "pulling 1a2b", "total": 100, "completed": 40},
                {"status": "pulling 1a2b", "total": 100, "completed": 100},
                {"status": "success"},
            ]
            pulled.add(body["model"])
            return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))
        if request.url.path == "/api/ps":
            return httpx.Response(
                200, json={"models": [{"name": "qwen2.5:1.5b", "size": 2 * 2**30, "size_vram": 0}]}
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def factory(transport: httpx.MockTransport, seen: list[str] | None = None):
    def make(base_url: str) -> httpx.AsyncClient:
        if seen is not None:
            seen.append(base_url)
        return httpx.AsyncClient(base_url=base_url, transport=transport)

    return make


def run(argv, env=OLLAMA_ENV, transport=None, stdin="", **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = main(
            argv,
            env,
            factory=factory(transport or ollama(), kw.get("seen")),
            stdin=io.StringIO(stdin),
            out=out,
        )
    return rc, out.getvalue(), err.getvalue()


def test_ollama_root_drops_the_openai_suffix() -> None:
    assert ollama_root("http://ollama:11434/v1/") == "http://ollama:11434"


def test_list_shows_the_catalogue_and_this_device() -> None:
    rc, out, _ = run(["list"], {**OLLAMA_ENV, "JARVIS_MODEL_LLM": "qwen2.5-1.5b"})
    assert rc == 0
    assert "faster-whisper-base-en" in out and "piper-lessac-medium" in out
    assert "qwen2.5:1.5b @ http://ollama:11434/v1" in out
    assert "env JARVIS_MODEL_LLM" in out


def test_list_reports_an_invalid_config() -> None:
    rc, out, _ = run(["list"], {"JARVIS_MODEL_LLM": "gpt-9"})
    assert rc == 1
    assert "unknown model 'gpt-9'" in out


def test_chat_streams_the_reply_and_shows_exact_stats() -> None:
    seen: list[str] = []
    rc, out, _ = run(["chat", "qwen2.5-1.5b"], stdin="Hi\n/reset\n/quit\n", seen=seen)
    assert rc == 0
    assert seen == ["http://ollama:11434"]  # Ollama's own API, beside /v1
    assert "jarvis> Hello there!" in out
    assert "15.0 tok/s" in out and "30 tokens" in out  # 30 tokens in 2 s
    assert "model load 1.50s" in out
    assert "(history cleared)" in out


def test_chat_sends_the_system_prompt_and_the_history() -> None:
    requests: list = []
    run(["chat", "qwen2.5-1.5b"], transport=ollama(requests=requests), stdin="Hi\nAgain\n")
    first, second = (body for path, body in requests if path == "/api/chat")
    assert first["messages"][0]["role"] == "system"
    assert [m["role"] for m in second["messages"]] == ["system", "user", "assistant", "user"]


def test_a_missing_model_points_at_pull() -> None:
    rc, _, err = run(["chat", "qwen2.5-1.5b"], transport=ollama(pulled=set()), stdin="Hi\n")
    assert rc == 2
    assert "run `models pull` first" in err


def test_pull_reports_progress() -> None:
    rc, out, _ = run(["pull", "qwen2.5-1.5b"], transport=ollama(pulled=set()))
    assert rc == 0
    assert "pulling 1a2b: 40%" in out and "pulling 1a2b: 100%" in out
    assert "is ready" in out


def test_pull_only_knows_ollama() -> None:
    rc, _, err = run(["pull", "piper-lessac-medium"])
    assert rc == 2 and "pull only knows Ollama" in err


def test_a_runtime_without_address_needs_base_url() -> None:
    rc, _, err = run(["chat", "qwen2.5-1.5b"], env={})
    assert rc == 2 and "JARVIS_RUNTIME_OLLAMA_URL" in err and "--base-url" in err
    rc, out, _ = run(["chat", "qwen2.5-1.5b", "--base-url", "http://pi:11434"], env={}, stdin="")
    assert rc == 0


def test_bench_compares_models_on_the_prompt_set() -> None:
    rc, out, err = run(["bench", "qwen2.5-1.5b"])
    assert rc == 0
    assert "qwen2.5-1.5b" in out and "15.0" in out and "2.00 GiB" in out
    assert "1.50" in out  # load time of the first request
    assert err.count(".") >= 5  # one dot per prompt


def test_bench_markdown_has_every_answer() -> None:
    rc, out, _ = run(["bench", "qwen2.5-1.5b", "--markdown"])
    assert rc == 0
    assert out.startswith("# Model bench")
    for prompt_id in ("greet", "plan", "note", "spar", "fact"):
        assert f"## {prompt_id}" in out
    assert "> Hello there!" in out


def test_bench_refuses_non_llm_models() -> None:
    rc, _, err = run(["bench", "piper-lessac-medium"])
    assert rc == 2 and "bench needs llms" in err


def test_other_runtimes_use_the_openai_stream_with_approximate_tokens() -> None:
    def openai(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        chunks = [{"choices": [{"delta": {"content": w}}]} for w in ("Hi", " you")]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=sse)

    async def probe():
        transport = httpx.MockTransport(openai)
        async with httpx.AsyncClient(base_url="http://s/v1/", transport=transport) as client:
            return await chat(client, "faelab", "m", [{"role": "user", "content": "Hi"}])

    reply = asyncio.run(probe())
    assert (reply.text, reply.tokens, reply.exact) == ("Hi you", 2, False)
    assert reply.ttft_s is not None


@pytest.mark.parametrize("argv", [["chat", "gpt-9"], ["bench", "gpt-9"]])
def test_unknown_models_are_named(argv) -> None:
    rc, _, err = run(argv)
    assert rc == 2 and "unknown model 'gpt-9'" in err


def test_bench_unloads_the_model_first_unless_warm() -> None:
    requests: list = []
    run(["bench", "qwen2.5-1.5b"], transport=ollama(requests=requests))
    assert requests[0] == ("/api/generate", {"model": "qwen2.5:1.5b", "keep_alive": 0})
    requests.clear()
    run(["bench", "qwen2.5-1.5b", "--warm"], transport=ollama(requests=requests))
    assert all(path != "/api/generate" for path, _ in requests)


def test_ad_hoc_ollama_models_can_be_tried_before_they_are_catalogued() -> None:
    requests: list = []
    rc, out, _ = run(
        ["chat", "ollama:qwen2.5:1.5b"], transport=ollama(requests=requests), stdin="Hi\n"
    )
    assert rc == 0 and "Hello there!" in out
    assert requests[0][1]["model"] == "qwen2.5:1.5b"


def test_other_ad_hoc_prefixes_are_refused_with_a_hint() -> None:
    rc, _, err = run(["chat", "speaches:whisper"])
    assert rc == 2 and "ollama:<name>" in err


def test_thinking_is_off_unless_asked_for() -> None:
    requests: list = []
    run(["chat", "qwen2.5-1.5b"], transport=ollama(requests=requests), stdin="Hi\n")
    run(["chat", "qwen2.5-1.5b", "--think"], transport=ollama(requests=requests), stdin="Hi\n")
    thinks = [body["think"] for path, body in requests if path == "/api/chat"]
    assert thinks == [False, True]


def test_bench_notes_the_cpu_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter([55.0, 71.4])
    monkeypatch.setattr("jarvis_agent.models.__main__.cpu_temp", lambda: next(readings))
    rc, out, _ = run(["bench", "qwen2.5-1.5b"])
    assert rc == 0 and "CPU °C" in out and "55→71" in out


def test_cpu_temp_reads_millidegrees(tmp_path) -> None:
    from jarvis_agent.models.probe import cpu_temp

    sensor = tmp_path / "temp"
    sensor.write_text("61234\n")
    assert cpu_temp(str(sensor)) == pytest.approx(61.234)
    assert cpu_temp(str(tmp_path / "missing")) is None


def test_pull_assigned_pulls_what_this_device_uses() -> None:
    requests: list = []
    env = {
        **OLLAMA_ENV,
        "JARVIS_MODEL_LLM": "qwen2.5-1.5b",
        "JARVIS_MODEL_TTS": "piper-lessac-medium",
        "JARVIS_RUNTIME_SPEACHES_URL": "http://speaches:8000/v1",
    }
    rc, out, _ = run(
        ["pull", "--assigned"], env=env, transport=ollama(pulled=set(), requests=requests)
    )
    assert rc == 0
    assert [body["model"] for path, body in requests if path == "/api/pull"] == ["qwen2.5:1.5b"]
    assert "tts: piper-lessac-medium runs on speaches, skipped" in out
    assert "Ready: qwen2.5:1.5b" in out


def test_pull_assigned_follows_an_explicit_model_override() -> None:
    requests: list = []
    env = {**OLLAMA_ENV, "JARVIS_MODEL_LLM": "qwen2.5-1.5b", "JARVIS_LLM_MODEL": "gemma3:1b"}
    run(["pull", "--assigned"], env=env, transport=ollama(pulled=set(), requests=requests))
    assert [body["model"] for path, body in requests if path == "/api/pull"] == ["gemma3:1b"]


def test_pull_assigned_with_nothing_assigned_is_fine() -> None:
    rc, out, _ = run(["pull", "--assigned"], env={})
    assert rc == 0 and "No Ollama models assigned" in out


def test_pull_needs_a_model_or_assigned() -> None:
    rc, _, err = run(["pull"])
    assert rc == 2 and "--assigned" in err


def test_the_home_profile_uses_qwen_on_the_ollama_service() -> None:
    from jarvis_agent.config import load_config

    llm = load_config({"JARVIS_PROFILE": "home"}).backend_settings().llm
    assert (llm.model, llm.base_url) == ("qwen2.5:1.5b", "http://ollama:11434/v1")
