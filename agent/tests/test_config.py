"""Layered config: validation, resolution order, env parity, profiles and the CLI."""

import io
from pathlib import Path

import pytest

from jarvis_agent.backends import BackendSettings
from jarvis_agent.config import ConfigError, available_profiles, load_config
from jarvis_agent.config.__main__ import main
from jarvis_agent.store import StoreSettings


def write(path: Path, text: str) -> str:
    path.write_text(text)
    return str(path)


# -- validation ------------------------------------------------------------------------


def test_defaults_need_no_config() -> None:
    config = load_config({})
    assert config.profile is None
    assert config.sources == ("defaults",)
    assert config.hardware.hailo == "auto"
    assert config.backend_settings() == BackendSettings()
    assert config.store_settings() == StoreSettings()


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    local = write(
        tmp_path / "jarvis.toml",
        """
        colour = "blue"
        [hardware]
        hailo = "maybe"
        [backends.llm]
        backend = "openai"
        [store]
        notes = "cloud"
        """,
    )
    with pytest.raises(ConfigError) as exc:
        load_config({"JARVIS_CONFIG": local, "JARVIS_HW_MIC": "sometimes"})
    problems = exc.value.problems
    assert len(problems) == 5, problems
    text = str(exc.value)
    assert "hardware.hailo" in text and f"file {local}" in text
    assert "hardware.mic" in text and "env JARVIS_HW_MIC" in text
    assert "backends.llm: the openai backend needs both base_url and model" in text
    assert "store.notes" in text
    assert "colour" in text


def test_unreadable_layers_are_all_reported(tmp_path: Path) -> None:
    broken = write(tmp_path / "broken.toml", "hardware = [")
    with pytest.raises(ConfigError) as exc:
        load_config({"JARVIS_CONFIG": broken, "JARVIS_PROFILE": "nope"})
    assert len(exc.value.problems) == 2
    assert "unknown profile 'nope' (known: dev, home, work)" in str(exc.value)


def test_missing_local_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="file not found"):
        load_config({"JARVIS_CONFIG": str(tmp_path / "absent.toml")})


# -- resolution order ------------------------------------------------------------------


def test_layers_resolve_in_order(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    write(
        profiles / "lab.toml",
        """
        [hardware]
        hailo = "off"
        imx500 = "off"
        mic = "off"
        [capabilities.vision]
        prefer = ["npu"]
        """,
    )
    local = write(
        tmp_path / "jarvis.toml",
        """
        profile = "lab"
        [hardware]
        imx500 = "on"
        mic = "on"
        [capabilities]
        vision = "on"
        """,
    )
    config = load_config({"JARVIS_CONFIG": local, "JARVIS_HW_MIC": "auto"}, profiles=profiles)
    assert config.profile == "lab"
    assert config.sources == ("defaults", "profile lab", f"file {local}", "env")
    assert config.hardware.hailo == "off"  # profile
    assert config.hardware.imx500 == "on"  # file over profile
    assert config.hardware.mic == "auto"  # env over file
    assert config.hardware.speaker == "auto"  # default
    # A table merges across layers: shorthand from the file, prefer from the profile.
    assert config.capabilities["vision"].enabled == "on"
    assert config.capabilities["vision"].prefer == ("npu",)


def test_env_profile_beats_the_file(tmp_path: Path) -> None:
    local = write(tmp_path / "jarvis.toml", 'profile = "home"\n')
    assert load_config({"JARVIS_CONFIG": local, "JARVIS_PROFILE": "Work"}).profile == "work"


def test_env_merges_into_a_file_role(tmp_path: Path) -> None:
    local = write(
        tmp_path / "jarvis.toml",
        '[backends.llm]\nbackend = "openai"\nbase_url = "http://ollama:11434/v1"\n',
    )
    config = load_config({"JARVIS_CONFIG": local, "JARVIS_LLM_MODEL": "qwen2.5:1.5b"})
    assert config.backends.llm.base_url == "http://ollama:11434/v1"
    assert config.backends.llm.model == "qwen2.5:1.5b"


# -- env parity with today's settings -------------------------------------------------

ENVS = [
    {},
    {"JARVIS_LLM_BACKEND": "", "JARVIS_STATE_DB": "  "},  # a copied .env.example
    {
        "JARVIS_LLM_BACKEND": "OpenAI",
        "JARVIS_LLM_BASE_URL": "http://ollama:11434/v1",
        "JARVIS_LLM_MODEL": "qwen2.5:1.5b",
        "JARVIS_LLM_API_KEY": "secret",
        "JARVIS_STT_BACKEND": "mock",
        "JARVIS_TTS_BACKEND": "openai",
        "JARVIS_TTS_BASE_URL": "http://speaches:8000/v1",
        "JARVIS_TTS_MODEL": "piper",
        "JARVIS_TTS_VOICE": "en_US-amy",
        "JARVIS_HEAVY_LLM_BACKEND": "MOCK",
        "JARVIS_STATE_DB": ":memory:",
        "JARVIS_NOTES_PROVIDER": "Faelab",
        "JARVIS_CALENDAR_PROVIDER": "local",
    },
]


@pytest.mark.parametrize("env", ENVS)
def test_env_reproduces_todays_settings(env: dict[str, str]) -> None:
    config = load_config(env)
    assert config.backend_settings() == BackendSettings.from_env(env)
    assert config.store_settings() == StoreSettings.from_env(env)


def test_env_rejects_what_today_rejects() -> None:
    env = {"JARVIS_HEAVY_LLM_BACKEND": "openai"}
    with pytest.raises(ValueError):
        BackendSettings.from_env(env)
    with pytest.raises(ConfigError, match="backends.heavy_llm"):
        load_config(env)


# -- profiles --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["home", "work", "dev"])
def test_shipped_profiles_load(name: str) -> None:
    assert name in available_profiles()
    config = load_config({"JARVIS_PROFILE": name})
    assert config.profile == name
    assert config.sources == ("defaults", f"profile {name}")


def test_work_profile_skips_the_accelerators() -> None:
    config = load_config({"JARVIS_PROFILE": "work"})
    assert (config.hardware.hailo, config.hardware.imx500) == ("off", "off")
    assert config.hardware.mic == "auto"
    assert config.capabilities["vision"].enabled == "off"


# -- CLI -------------------------------------------------------------------------------


def test_cli_masks_secrets_and_reports_capabilities() -> None:
    out = io.StringIO()
    env = {
        "JARVIS_LLM_BACKEND": "openai",
        "JARVIS_LLM_BASE_URL": "http://ollama:11434/v1",
        "JARVIS_LLM_MODEL": "qwen2.5:1.5b",
        "JARVIS_LLM_API_KEY": "hunter2",
    }
    assert main(env, probes={}, out=out) == 0
    text = out.getvalue()
    assert "hunter2" not in text
    assert '"api_key": "**********"' in text
    assert "notes" in text and "enabled" in text
    assert "voice" in text and "hardware mic (not detected)" in text


def test_cli_fails_on_invalid_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main({"JARVIS_HW_HAILO": "maybe"}, probes={}, out=io.StringIO()) == 1
    assert "hardware.hailo" in capsys.readouterr().err


def test_cli_rejects_unknown_capabilities(capsys: pytest.CaptureFixture[str]) -> None:
    assert main({"JARVIS_CAP_TELEPORT": "on"}, probes={}, out=io.StringIO()) == 1
    err = capsys.readouterr().err
    assert "capabilities.teleport: unknown capability" in err
    assert "(from env JARVIS_CAP_TELEPORT)" in err
