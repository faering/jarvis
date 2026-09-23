"""Backends for any server speaking the OpenAI HTTP API (Ollama, speaches, cloud, ...).

Each takes an ``httpx.AsyncClient`` whose ``base_url`` ends in ``/v1``; switching between
dev and Pi servers is only a matter of base URL and model name. Every failure surfaces as
``BackendError``.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from jarvis_agent.backends.base import BackendError, ChatMessage


class OpenAILLM:
    """``POST /chat/completions``, with SSE streaming for ``stream``."""

    def __init__(self, client: httpx.AsyncClient, model: str) -> None:
        self._client = client
        self._model = model

    async def chat(self, messages: list[ChatMessage]) -> str:
        body = {"model": self._model, "messages": messages}
        data = _json("llm", await _post("llm", self._client, "chat/completions", json=body))
        try:
            return _text("llm", data["choices"][0]["message"]["content"], data)
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError("llm", f"unexpected response shape: {data!r}") from exc

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        body = {"model": self._model, "messages": messages, "stream": True}
        try:
            async with self._client.stream("POST", "chat/completions", json=body) as response:
                await _raise_for_status("llm", response)
                async for line in response.aiter_lines():
                    event = _parse_sse_line(line)
                    if event is _DONE:
                        return
                    if isinstance(event, str):
                        yield event
        except httpx.TransportError as exc:
            raise BackendError("llm", f"request failed: {exc!r}") from exc
        # EOF without the [DONE] sentinel: the reply may be truncated, so don't pass it off
        # as complete.
        raise BackendError("llm", "stream ended without [DONE]")


class OpenAISTT:
    """``POST /audio/transcriptions`` (multipart upload)."""

    def __init__(self, client: httpx.AsyncClient, model: str) -> None:
        self._client = client
        self._model = model

    async def transcribe(self, audio: bytes, *, audio_format: str = "wav") -> str:
        files = {"file": (f"audio.{audio_format}", audio, f"audio/{audio_format}")}
        form = {"model": self._model, "response_format": "json"}
        response = await _post("stt", self._client, "audio/transcriptions", files=files, data=form)
        data = _json("stt", response)
        try:
            return _text("stt", data["text"], data)
        except (KeyError, TypeError) as exc:
            raise BackendError("stt", f"unexpected response shape: {data!r}") from exc


class OpenAITTS:
    """``POST /audio/speech``; always requests WAV."""

    def __init__(self, client: httpx.AsyncClient, model: str, voice: str | None = None) -> None:
        self._client = client
        self._model = model
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        body = {"model": self._model, "input": text, "response_format": "wav"}
        if self._voice:
            body["voice"] = self._voice
        response = await _post("tts", self._client, "audio/speech", json=body)
        return response.content


_DONE = object()


def _parse_sse_line(line: str) -> str | object | None:
    """One SSE line -> its text delta, ``_DONE`` at end of stream, or None to skip it."""
    if not line.startswith("data:"):
        return None  # blank separators, comments, other SSE fields
    payload = line.removeprefix("data:").strip()
    if payload == "[DONE]":
        return _DONE
    try:
        choices = json.loads(payload)["choices"]
        content = choices[0]["delta"].get("content") if choices else None
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise BackendError("llm", f"malformed stream event: {payload!r}") from exc
    if content is None or content == "":
        return None
    if not isinstance(content, str):
        raise BackendError("llm", f"malformed stream event: {payload!r}")
    return content


async def _post(role: str, client: httpx.AsyncClient, path: str, **kwargs: Any) -> httpx.Response:
    try:
        response = await client.post(path, **kwargs)
    except httpx.TransportError as exc:
        raise BackendError(role, f"request failed: {exc!r}") from exc
    await _raise_for_status(role, response)
    return response


async def _raise_for_status(role: str, response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = (await response.aread()).decode(errors="replace")[:500]
    raise BackendError(
        role,
        f"HTTP {response.status_code} from {response.request.url}: {detail}",
        status_code=response.status_code,
    )


def _text(role: str, value: Any, data: Any) -> str:
    """A reply field must be a string (``null`` or other types break the role contract)."""
    if not isinstance(value, str):
        raise BackendError(role, f"unexpected response shape: {data!r}")
    return value


def _json(role: str, response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise BackendError(role, f"response is not JSON: {response.text[:200]!r}") from exc
