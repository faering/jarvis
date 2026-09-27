"""The agent runtime: backends, router, speech, state store and the voice loop.

``start_runtime()`` builds everything from ``JARVIS_*`` env vars (see ``backends.config``
and ``store.config``); ``lifespan`` ties it to the FastAPI app. Audio output defaults to
``NullSink``: the real speaker sink, like the mic source, is Pi hardware.

``start_logging()`` configures logging from the ``[logging]`` config section; ``lifespan``
calls it unless the entrypoint (``python -m jarvis_agent``) already did.
"""

import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from jarvis_agent import logs
from jarvis_agent.backends import Backends, BackendSettings, build_backends
from jarvis_agent.config import ConfigError, load_config
from jarvis_agent.logs import LogSettings, kv
from jarvis_agent.logs.setup import Logging
from jarvis_agent.loop import VoiceLoop
from jarvis_agent.routing import Router, build_router
from jarvis_agent.speech import AudioSink, NullSink, SpeechQueue
from jarvis_agent.store import State, StoreSettings, open_state
from jarvis_agent.version import build_info

log = logging.getLogger(__name__)
LOG_ENV = ("JARVIS_LOG_DIR", "JARVIS_LOG_LEVEL")


def log_settings(environ: Mapping[str, str] | None = None) -> tuple[LogSettings, list[str]]:
    """The ``[logging]`` config, plus the config's problems if it is invalid: logging then
    still starts, from the logging env vars alone (or the defaults)."""
    env = os.environ if environ is None else environ
    try:
        return load_config(env).logging, []
    except ConfigError as exc:
        problems = exc.problems
    try:
        return load_config({k: env[k] for k in LOG_ENV if k in env}).logging, problems
    except ConfigError as exc:
        return LogSettings(), problems + exc.problems


def start_logging(environ: Mapping[str, str] | None = None) -> Logging:
    settings, problems = log_settings(environ)
    installed = logs.configure(settings, version=build_info()["version"])
    if problems:
        log.error(
            "invalid config, logging from env and defaults", extra=kv(problems="; ".join(problems))
        )
    log.info(
        "agent starting",
        extra=kv(
            **{"service.version": build_info()["version"]},
            log_dir=settings.dir or "",
            log_level=settings.level,
        ),
    )
    return installed


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
    owns_logging = logs.active() is None  # plain `uvicorn jarvis_agent.main:app`, tests
    if owns_logging:
        start_logging()
    try:
        try:
            runtime = await start_runtime()
        except Exception:
            log.critical("cannot start the runtime", exc_info=True)
            raise
        app.state.runtime = runtime
        log.info("agent ready")
        try:
            yield
        finally:
            del app.state.runtime
            await runtime.aclose()
            log.info("agent stopped")
    finally:
        if owns_logging:
            logs.shutdown()
