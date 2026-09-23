"""OpenAI-compatible backends against httpx.MockTransport: request shape and parsing."""

import json
from collections.abc import Awaitable, Callable

import httpx
import pytest

from jarvis_agent.backends import BackendError, ChatMessage
from jarvis_agent.backends.openai_compat import OpenAILLM, OpenAISTT, OpenAITTS

pytestmark = pytest.mark.anyio

BASE_URL = "http://server:1234/v1"
MESSAGES: list[ChatMessage] = [{"role": "user", "content": "hi"}]
Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE_URL)


def _sse(*events: str) -> bytes:
    return "".join(f"data: {event}\n\n" for event in events).encode()


async def test_chat_request_and_reply() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    reply = await OpenAILLM(_client(handler), "qwen").chat(MESSAGES)

    assert reply == "hello"
    assert seen[0].method == "POST"
    assert seen[0].url == f"{BASE_URL}/chat/completions"
    assert json.loads(seen[0].content) == {"model": "qwen", "messages": MESSAGES}


async def test_stream_yields_deltas_until_done() -> None:
    seen: list[httpx.Request] = []
    body = _sse(
        '{"choices":[{"delta":{"role":"assistant"}}]}',
        '{"choices":[{"delta":{"content":"Hel"}}]}',
        '{"choices":[{"delta":{"content":"lo"}}]}',
        '{"choices":[]}',
        "[DONE]",
        '{"choices":[{"delta":{"content":"after done"}}]}',
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b": keep-alive\n\n" + body)

    chunks = [chunk async for chunk in OpenAILLM(_client(handler), "qwen").stream(MESSAGES)]

    assert chunks == ["Hel", "lo"]
    assert json.loads(seen[0].content)["stream"] is True


async def test_stream_malformed_event_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_sse("not json"))

    with pytest.raises(BackendError, match="malformed stream event"):
        _ = [chunk async for chunk in OpenAILLM(_client(handler), "qwen").stream(MESSAGES)]


async def test_transcribe_sends_multipart() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hello there"})

    text = await OpenAISTT(_client(handler), "whisper").transcribe(b"RIFFdata")

    assert text == "hello there"
    request = seen[0]
    assert request.url == f"{BASE_URL}/audio/transcriptions"
    assert request.headers["content-type"].startswith("multipart/form-data")
    body = request.content
    assert b'name="model"\r\n\r\nwhisper' in body
    assert b'name="file"; filename="audio.wav"' in body
    assert b"Content-Type: audio/wav" in body
    assert b"RIFFdata" in body


async def test_synthesize_request_and_bytes() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"RIFF-audio")

    audio = await OpenAITTS(_client(handler), "piper", voice="amy").synthesize("hi")

    assert audio == b"RIFF-audio"
    assert seen[0].url == f"{BASE_URL}/audio/speech"
    assert json.loads(seen[0].content) == {
        "model": "piper",
        "input": "hi",
        "response_format": "wav",
        "voice": "amy",
    }


async def test_synthesize_omits_unset_voice() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"")

    await OpenAITTS(_client(handler), "piper").synthesize("hi")

    assert "voice" not in json.loads(seen[0].content)


def _error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404, text="model not found")


def _unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _calls(handler: Handler) -> dict[str, Callable[[], Awaitable[object]]]:
    client = _client(handler)
    return {
        "chat": lambda: OpenAILLM(client, "m").chat(MESSAGES),
        "transcribe": lambda: OpenAISTT(client, "m").transcribe(b""),
        "synthesize": lambda: OpenAITTS(client, "m").synthesize("x"),
    }


@pytest.mark.parametrize("call", ["chat", "transcribe", "synthesize"])
async def test_http_error_raises_backend_error(call: str) -> None:
    with pytest.raises(BackendError, match="HTTP 404.*model not found") as info:
        await _calls(_error)[call]()
    assert info.value.status_code == 404


@pytest.mark.parametrize("call", ["chat", "transcribe", "synthesize"])
async def test_unreachable_server_raises_backend_error(call: str) -> None:
    with pytest.raises(BackendError, match="request failed"):
        await _calls(_unreachable)[call]()


@pytest.mark.parametrize("handler", [_error, _unreachable])
async def test_stream_errors_raise_backend_error(handler: Handler) -> None:
    with pytest.raises(BackendError):
        _ = [chunk async for chunk in OpenAILLM(_client(handler), "m").stream(MESSAGES)]


async def test_unexpected_response_shape_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(BackendError, match="unexpected response shape"):
        await OpenAILLM(_client(handler), "m").chat(MESSAGES)
