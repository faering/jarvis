"""The capabilities Jarvis ships with. MCP-discovered ones (#68) will join this list."""

from jarvis_agent.capabilities.manifest import Manifest, ProviderSpec, requires
from jarvis_agent.routing import ComputeLayer


def _store_domain(name: str, description: str) -> Manifest:
    # Local = the SQLite store serves this domain (JARVIS_<DOMAIN>_PROVIDER=local); faelab =
    # its MCP tool. The store setting picks one, so local-first always agrees with it.
    return Manifest(
        name,
        description,
        providers=(
            ProviderSpec("local", ComputeLayer.CPU, requires=requires(state=[name])),
            ProviderSpec(
                "faelab",
                ComputeLayer.REMOTE,
                source="faelab",
                requires=requires(tools=[f"faelab.{name}"]),
            ),
        ),
    )


BUILTIN: tuple[Manifest, ...] = (
    Manifest(
        "voice",
        "listen and talk back",
        requires=requires(hardware=["mic", "speaker"], backends=["stt", "llm", "tts"]),
        providers=(ProviderSpec("local", ComputeLayer.CPU),),
    ),
    Manifest(
        "vision",
        "see: detect objects and people",
        requires=requires(backends=["vision"]),
        providers=(
            ProviderSpec("camera", ComputeLayer.CAMERA, requires=requires(hardware=["imx500"])),
            ProviderSpec("npu", ComputeLayer.NPU, requires=requires(hardware=["hailo"])),
        ),
    ),
    _store_domain("notes", "take and recall notes"),
    _store_domain("todo", "keep a todo list"),
    _store_domain("calendar", "manage the calendar"),
    Manifest(
        "heavy_reasoning",
        "think hard off the hot path (larger model)",
        providers=(
            ProviderSpec("remote", ComputeLayer.REMOTE, requires=requires(backends=["heavy_llm"])),
        ),
    ),
)
