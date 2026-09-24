"""Capability resolution: preferences, clean disabling with reasons, and config checks."""

import pytest

from jarvis_agent.capabilities import (
    BUILTIN,
    Available,
    Manifest,
    ProviderSpec,
    check_config,
    requires,
    resolve,
)
from jarvis_agent.config import CapabilityConfig, ConfigError, load_config
from jarvis_agent.hardware import HARDWARE, HardwareStatus
from jarvis_agent.routing import ComputeLayer


def hardware(*present: str) -> dict[str, HardwareStatus]:
    return {
        name: HardwareStatus(True, "on in config")
        if name in present
        else HardwareStatus(False, "not detected")
        for name in HARDWARE
    }


def available(
    *present: str, env: dict[str, str] | None = None, tools: tuple[str, ...] = ()
) -> Available:
    return Available.from_config(load_config(env or {}), hardware(*present), tools)


def test_off_device_defaults() -> None:
    report = resolve(available())
    assert set(report.enabled) == {"notes", "todo", "calendar"}
    assert report.enabled["notes"].provider.name == "local"
    assert report.disabled["voice"].reason == (
        "missing hardware mic (not detected), hardware speaker (not detected)"
    )
    assert report.disabled["heavy_reasoning"].reason == (
        "no provider available (remote: missing backend heavy_llm (not configured))"
    )
    assert report.required_unmet == []


def test_voice_on_a_pi_with_audio() -> None:
    report = resolve(available("mic", "speaker"))
    assert report.enabled["voice"].provider.layer == ComputeLayer.CPU


def test_vision_follows_the_preference_order() -> None:
    both = available("imx500", "hailo")
    assert resolve(both).enabled["vision"].provider.name == "camera"  # manifest order
    prefer_npu = {"vision": CapabilityConfig(prefer=("npu", "camera"))}
    chosen = resolve(both, prefer_npu).enabled["vision"].provider
    assert (chosen.name, chosen.layer) == ("npu", ComputeLayer.NPU)
    # Falls through to the next preferred provider when the first is unsatisfiable.
    assert resolve(available("imx500"), prefer_npu).enabled["vision"].provider.name == "camera"


def test_prefer_is_also_an_allow_list() -> None:
    only_npu = {"vision": CapabilityConfig(prefer=("npu",))}
    disabled = resolve(available("imx500"), only_npu).disabled["vision"]
    assert disabled.reason == "no provider available (npu: missing hardware hailo (not detected))"


def test_off_in_config_wins_over_available_hardware() -> None:
    report = resolve(available("imx500"), {"vision": CapabilityConfig(enabled="off")})
    assert report.disabled["vision"].reason == "off in config"
    assert not report.disabled["vision"].required


def test_required_but_unsatisfiable_is_disabled_not_raised() -> None:
    report = resolve(available(), {"voice": CapabilityConfig(enabled="on")})
    assert "voice" not in report.enabled
    assert [d.name for d in report.required_unmet] == ["voice"]


def test_heavy_reasoning_needs_a_heavy_backend() -> None:
    report = resolve(available(env={"JARVIS_HEAVY_LLM_BACKEND": "mock"}))
    assert report.enabled["heavy_reasoning"].provider.layer == ComputeLayer.REMOTE


def test_store_domain_on_faelab_needs_its_tool() -> None:
    env = {"JARVIS_NOTES_PROVIDER": "faelab"}
    disabled = resolve(available(env=env)).disabled["notes"]
    assert disabled.reason == (
        "no provider available (local: missing state notes (served by faelab); "
        "faelab: missing tool faelab.notes (not available))"
    )
    enabled = resolve(available(env=env, tools=("faelab.notes",))).enabled["notes"]
    assert (enabled.provider.name, enabled.provider.source) == ("faelab", "faelab")


def test_unknown_names_in_config_are_config_errors() -> None:
    settings = {
        "teleport": CapabilityConfig(),
        "vision": CapabilityConfig(prefer=("laser", "npu")),
    }
    assert len(check_config(settings)) == 2
    with pytest.raises(ConfigError, match="unknown provider laser"):
        resolve(available(), settings)


def test_home_profile_requires_heavy_reasoning() -> None:
    config = load_config({"JARVIS_PROFILE": "home"})
    report = resolve(Available.from_config(config, hardware()), config.capabilities)
    assert [d.name for d in report.required_unmet] == ["heavy_reasoning"]


def test_custom_manifests() -> None:
    lamp = Manifest(
        "lamp",
        "light up",
        providers=(ProviderSpec("gpio", ComputeLayer.CPU, requires=requires(tools=["gpio"])),),
    )
    report = resolve(available(tools=("gpio",)), manifests=(lamp,))
    assert set(report.enabled) == {"lamp"}


def test_manifests_validate_their_requirements() -> None:
    with pytest.raises(ValueError, match="unknown hardware: lidar"):
        requires(hardware=["lidar"])
    with pytest.raises(ValueError, match="uniquely named providers"):
        Manifest("x", "x", providers=())
    assert len({m.name for m in BUILTIN}) == len(BUILTIN)
