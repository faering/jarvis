"""The agent runtime: backends, router, speech, state store and the voice loop.

``start_runtime()`` builds everything from ``JARVIS_*`` env vars (see ``backends.config``
and ``store.config``); ``lifespan`` ties it to the FastAPI app. Audio output defaults to
``NullSink``: the real speaker sink, like the mic source, is Pi hardware.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from jarvis_agent.backends import Backends, BackendSettings, build_backends
from jarvis_agent.loop import VoiceLoop
from jarvis_agent.routing import Router, build_router
from jarvis_agent.speech import AudioSink, NullSink, SpeechQueue
from jarvis_agent.store import State, StoreSettings, open_state


@dataclass
class Runtime:
    backends: Backends
    router: Router
    speech: SpeechQueue
    state: State
    loop: VoiceLoop
    _stack: AsyncExitStack

    async def aclose(self) -> None:
        """Shut down in reverse start order: loop, offloaded work, speech, store, clients."""
        await self._stack.aclose()


async def start_runtime(
    *,
    backend_settings: BackendSettings | None = None,
    store_settings: StoreSettings | None = None,
    sink: AudioSink | None = None,
) -> Runtime:
    """Build and start everything; if any step fails, what already started is closed."""
    async with AsyncExitStack() as stack:
        backends = build_backends(backend_settings)
        stack.push_async_callback(backends.aclose)
        state = await open_state(store_settings)
        stack.push_async_callback(state.aclose)
        speech = SpeechQueue(backends.tts, sink or NullSink())
        speech.start()
        stack.push_async_callback(speech.aclose)
        router = build_router(backends)
        stack.push_async_callback(router.aclose)
        loop = VoiceLoop(router, speech, backends.stt, state.memory)
        loop.start()
        stack.push_async_callback(loop.aclose)
        return Runtime(backends, router, speech, state, loop, stack.pop_all())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = await start_runtime()
    app.state.runtime = runtime
    try:
        yield
    finally:
        del app.state.runtime
        await runtime.aclose()
