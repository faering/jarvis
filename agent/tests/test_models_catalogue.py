"""Model catalogue (#56): the shipped data, role resolution into backends, and config."""

import asyncio
import re
from pathlib import Path

import pytest

from jarvis_agent.backends import BackendSettings, RoleSettings
from jarvis_agent.config import ConfigError, load_config
from jarvis_agent.models import (
    WIRED,
    Catalogue,
    ModelProblems,
    RuntimeConfig,
    load_catalogue,
    resolve_backends,
)
from jarvis_agent.runtime import start_runtime

REPO = Path(__file__).resolve().parents[2]
OLLAMA = {"ollama": RuntimeConfig(base_url="http://ollama:11434/v1")}

CATALOGUE = Catalogue.model_validate(
    {
        "model": {
            "small": {"roles": ["llm", "heavy_llm"], "runtime": "ollama", "source": "small:1b"},
            "ears": {"roles": ["stt"], "runtime": "speaches", "source": "whisper"},
            "mouth": {"roles": ["tts"], "runtime": "speaches", "source": "piper", "voice": "v"},
            "eyes": {"roles": ["vlm"], "runtime": "ollama", "source": "eyes:3b"},
            "npu": {"roles": ["llm"], "runtime": "hailo", "source": "qwen.hef"},
        }
    }
)


def resolve(models, backends=None, runtimes=OLLAMA, catalogue=CATALOGUE):
    return resolve_backends(models, runtimes, backends or BackendSettings(), catalogue)


# -- the shipped catalogue ----------------------------------------------------------------


def test_shipped_catalogue_is_valid_and_covers_the_wired_dev_roles() -> None:
    catalogue = load_catalogue()
    for role in ("llm", "stt", "tts"):
        assert catalogue.for_role(role), f"no {role} model in the catalogue"


def test_dev_stack_defaults_are_catalogue_models() -> None:
    compose = (REPO / "docker-compose.yml").read_text()
    defaults = dict(re.findall(r"(JARVIS_MODEL_\w+): \$\{\1:-([^}]+)\}", compose))
    assert defaults, "docker-compose.yml assigns no models"
    catalogue = load_catalogue()
    for var, model_id in defaults.items():
        role = var.removeprefix("JARVIS_MODEL_").lower()
        assert role in catalogue.model[model_id].roles, f"{var}={model_id}"


def test_voice_is_only_for_tts_models() -> None:
    with pytest.raises(ValueError, match="voice is only for tts"):
        Catalogue.model_validate(
            {"model": {"x": {"roles": ["llm"], "runtime": "ollama", "source": "x", "voice": "v"}}}
        )


# -- resolution ---------------------------------------------------------------------------


def test_assignment_fills_the_role_from_the_catalogue_and_runtime() -> None:
    llm = resolve({"llm": "small"}).llm
    assert (llm.backend, llm.base_url, llm.model) == (
        "openai",
        "http://ollama:11434/v1",
        "small:1b",
    )


def test_tts_gets_the_catalogue_voice_and_the_runtime_key() -> None:
    runtimes = {"speaches": RuntimeConfig(base_url="http://s/v1", api_key="k")}
    tts = resolve({"tts": "mouth"}, runtimes=runtimes).tts
    assert (tts.model, tts.voice, tts.api_key.get_secret_value()) == ("piper", "v", "k")


def test_explicit_fields_win_one_by_one() -> None:
    backends = BackendSettings(llm=RoleSettings.model_validate({"model": "other:3b"}))
    llm = resolve({"llm": "small"}, backends=backends).llm
    assert (llm.base_url, llm.model) == ("http://ollama:11434/v1", "other:3b")


def test_an_explicit_mock_keeps_the_role_mocked() -> None:
    backends = BackendSettings(llm=RoleSettings(backend="mock"))
    assert resolve({"llm": "small"}, backends=backends).llm.backend == "mock"


def test_unassigned_and_unwired_roles_are_left_alone() -> None:
    settings = resolve({"vlm": "eyes"})  # valid, but vision isn't wired yet
    assert settings == BackendSettings()
    assert "vlm" not in WIRED


def test_every_problem_is_reported_per_role() -> None:
    with pytest.raises(ModelProblems) as exc:
        resolve(
            {"llm": "gpt-9", "stt": "small", "tts": "mouth", "heavy_llm": "npu"},
            runtimes=OLLAMA,
        )
    problems = exc.value.problems
    assert "unknown model 'gpt-9'" in problems["llm"]
    assert "catalogue models for llm: npu, small" in problems["llm"]
    assert "is not a stt model" in problems["stt"]
    assert "no address here" in problems["tts"] and "JARVIS_RUNTIME_SPEACHES_URL" in problems["tts"]
    assert "not a heavy_llm model" in problems["heavy_llm"]


def test_npu_models_are_not_wired_yet() -> None:
    with pytest.raises(ModelProblems, match="runs on hailo, which isn't wired yet"):
        resolve({"llm": "npu"})


# -- config layers ------------------------------------------------------------------------


def test_env_assigns_models_and_runtimes() -> None:
    config = load_config(
        {
            "JARVIS_MODEL_LLM": "qwen2.5-1.5b",
            "JARVIS_RUNTIME_OLLAMA_URL": "http://ollama:11434/v1",
            "JARVIS_RUNTIME_FAELAB_VLLM_URL": "http://faelab/v1",
            "JARVIS_RUNTIME_FAELAB_VLLM_API_KEY": "secret",
        }
    )
    assert config.models == {"llm": "qwen2.5-1.5b"}
    assert config.runtimes["faelab_vllm"].api_key.get_secret_value() == "secret"
    assert config.backend_settings().llm.model == "qwen2.5:1.5b"


def test_a_profile_assigns_models(tmp_path: Path) -> None:
    (tmp_path / "pi.toml").write_text(
        '[models]\nllm = "qwen2.5-1.5b"\n[runtimes.ollama]\nbase_url = "http://ollama:11434/v1"\n'
    )
    config = load_config({"JARVIS_PROFILE": "pi"}, profiles=tmp_path)
    assert config.backend_settings().llm.base_url == "http://ollama:11434/v1"
    overridden = load_config(
        {"JARVIS_PROFILE": "pi", "JARVIS_LLM_MODEL": "llama3.2:3b"}, profiles=tmp_path
    )
    assert overridden.backend_settings().llm.model == "llama3.2:3b"


def test_bad_assignments_fail_config_naming_their_layer() -> None:
    with pytest.raises(ConfigError) as exc:
        load_config({"JARVIS_MODEL_LLM": "gpt-9"})
    assert exc.value.problems == [
        "models.llm: unknown model 'gpt-9' (catalogue models for llm: qwen2.5-1.5b)"
        " (from env JARVIS_MODEL_LLM)"
    ]


def test_unknown_roles_fail_config() -> None:
    with pytest.raises(ConfigError, match="models.brain"):
        load_config({"JARVIS_MODEL_BRAIN": "qwen2.5-1.5b"})


def test_the_runtime_refuses_a_bad_assignment_before_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JARVIS_MODEL_LLM", "gpt-9")
    with pytest.raises(ConfigError, match="unknown model 'gpt-9'"):
        asyncio.run(start_runtime())
