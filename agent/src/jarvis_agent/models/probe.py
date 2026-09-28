"""Talk to one model directly, timing it: the engine behind ``models chat`` and ``bench``.

Ollama models go through Ollama's own ``/api/chat``, whose final message carries exact
token counts and durations (nanoseconds). Any other runtime goes through the
OpenAI-compatible stream; there, tokens are counted as streamed chunks, an approximation.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from jarvis_agent.backends import BackendError, ChatMessage
from jarvis_agent.backends.openai_compat import OpenAILLM

NS = 1e9


@dataclass(frozen=True)
class Reply:
    text: str
    total_s: float
    ttft_s: float | None  # time to the first text
    tokens: int | None
    tokens_per_s: float | None
    load_s: float | None = None  # Ollama: time spent loading the model for this request
    exact: bool = True  # False: tokens are streamed chunks, not the model's count


class ProbeError(RuntimeError):
    """The model couldn't be reached or answered badly; the message says what to do."""


def ollama_root(base_url: str) -> str:
    """Ollama's own API sits beside its OpenAI ``/v1``."""
    return base_url.rstrip("/").removesuffix("/v1")


async def chat(
    client: httpx.AsyncClient,
    runtime: str,
    source: str,
    messages: list[ChatMessage],
    on_text: Callable[[str], None] = lambda _: None,
) -> Reply:
    """Send ``messages`` to the model, streaming text to ``on_text``; returns the timings."""
    if runtime == "ollama":
        return await _ollama_chat(client, source, messages, on_text)
    return await _openai_chat(client, source, messages, on_text)


async def _ollama_chat(
    client: httpx.AsyncClient,
    source: str,
    messages: list[ChatMessage],
    on_text: Callable[[str], None],
) -> Reply:
    body = {"model": source, "messages": messages, "stream": True}
    start = time.perf_counter()
    first: float | None = None
    parts: list[str] = []
    final: dict = {}
    try:
        async with client.stream("POST", "/api/chat", json=body) as response:
            if response.status_code != 200:
                await response.aread()
                raise ProbeError(_ollama_error(response, source))
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if error := event.get("error"):
                    raise ProbeError(f"ollama: {error}")
                if text := event.get("message", {}).get("content", ""):
                    first = first or time.perf_counter()
                    parts.append(text)
                    on_text(text)
                if event.get("done"):
                    final = event
    except httpx.TransportError as exc:
        raise ProbeError(f"can't reach ollama at {client.base_url}: {exc!r}") from exc
    total = time.perf_counter() - start
    tokens, eval_ns = final.get("eval_count"), final.get("eval_duration")
    return Reply(
        text="".join(parts),
        total_s=total,
        ttft_s=None if first is None else first - start,
        tokens=tokens,
        tokens_per_s=tokens / (eval_ns / NS) if tokens and eval_ns else None,
        load_s=final["load_duration"] / NS if "load_duration" in final else None,
    )


def _ollama_error(response: httpx.Response, source: str) -> str:
    try:
        detail = response.json().get("error", response.text)
    except ValueError:
        detail = response.text
    if response.status_code == 404:
        return f"ollama doesn't have {source!r} yet ({detail}); run `models pull` first"
    return f"ollama answered {response.status_code}: {detail}"


async def _openai_chat(
    client: httpx.AsyncClient,
    source: str,
    messages: list[ChatMessage],
    on_text: Callable[[str], None],
) -> Reply:
    start = time.perf_counter()
    first: float | None = None
    parts: list[str] = []
    try:
        async for text in OpenAILLM(client, source).stream(messages):
            first = first or time.perf_counter()
            parts.append(text)
            on_text(text)
    except BackendError as exc:
        raise ProbeError(str(exc)) from exc
    end = time.perf_counter()
    gen = end - first if first is not None else 0.0
    return Reply(
        text="".join(parts),
        total_s=end - start,
        ttft_s=None if first is None else first - start,
        tokens=len(parts),
        tokens_per_s=len(parts) / gen if gen > 0 else None,
        exact=False,
    )


async def pull(client: httpx.AsyncClient, source: str, on_progress: Callable[[str], None]) -> None:
    """Ollama: download ``source``, reporting progress lines like ``pulling 1a2b: 40%``."""
    last = ""
    try:
        async with client.stream(
            "POST", "/api/pull", json={"model": source, "stream": True}, timeout=None
        ) as response:
            if response.status_code != 200:
                await response.aread()
                raise ProbeError(_ollama_error(response, source))
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if error := event.get("error"):
                    raise ProbeError(f"ollama: {error}")
                status = event.get("status", "")
                if event.get("total"):
                    status += f": {100 * event.get('completed', 0) // event['total']}%"
                if status != last:
                    on_progress(status)
                    last = status
    except httpx.TransportError as exc:
        raise ProbeError(f"can't reach ollama at {client.base_url}: {exc!r}") from exc


async def unload(client: httpx.AsyncClient, source: str) -> None:
    """Ollama: drop the model from memory, so the next request measures a cold load."""
    try:
        await client.post("/api/generate", json={"model": source, "keep_alive": 0})
    except httpx.HTTPError:
        pass  # best effort: at worst the load time reads as warm


async def loaded_size(client: httpx.AsyncClient, source: str) -> tuple[int, int] | None:
    """Ollama: (bytes in memory, of which on a GPU/NPU) for a loaded model, from ``/api/ps``."""
    try:
        response = await client.get("/api/ps")
        response.raise_for_status()
        running = response.json().get("models", [])
    except httpx.HTTPError, ValueError:
        return None
    for model in running:
        if source in (model.get("name"), model.get("model")):
            return model.get("size", 0), model.get("size_vram", 0)
    return None
