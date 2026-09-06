"""Tests for the isolated SLM configuration loader."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import slm.config as config_module
from slm.config import SLMConfig, load_slm_config, required_context_tokens


SLM_VARIABLES = (
    "SLM_BASE_URL",
    "SLM_MODEL_NAME",
    "SLM_API_KEY",
    "SLM_STRUCTURED_MODE",
    "SLM_MAX_PROMPT_CHARS",
    "SLM_MAX_OUTPUT_TOKENS",
    "SLM_RUN_MAX_REQUESTS",
    "SLM_RUN_MAX_TOTAL_TOKENS",
    "SLM_REQUEST_TIMEOUT",
    "SLM_CONTEXT_PROBE",
)


@pytest.fixture(autouse=True)
def isolated_slm_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for variable_name in SLM_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    monkeypatch.setattr(config_module, "_SLM_ENV_PATH", tmp_path / ".env.slm")


def test_load_slm_config_uses_documented_defaults() -> None:
    assert load_slm_config() == SLMConfig(
        base_url="https://api.siliconflow.com/v1",
        model_name="Qwen/Qwen2.5-7B-Instruct",
        api_key="",
        structured_mode="json_object",
        max_prompt_chars=60_000,
        max_output_tokens=8_192,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=900,
        context_probe=True,
    )


def test_required_context_tokens_covers_prompt_and_output_budgets() -> None:
    """The guard must demand room for the whole prompt plus the whole output."""
    required = required_context_tokens(load_slm_config())

    # 60_000 chars / 4.0 chars-per-token + 8_192 output tokens.
    assert required == 23_192


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("ON", True),
        ("0", False),
        ("false", False),
        ("Off", False),
    ],
)
def test_context_probe_flag_accepts_boolean_spellings(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    expected: bool,
) -> None:
    monkeypatch.setenv("SLM_CONTEXT_PROBE", raw_value)

    assert load_slm_config().context_probe is expected


def test_context_probe_flag_rejects_non_boolean_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLM_CONTEXT_PROBE", "maybe")

    with pytest.raises(ValueError, match="SLM_CONTEXT_PROBE"):
        load_slm_config()


def test_slm_config_is_frozen() -> None:
    loaded_config = load_slm_config()

    with pytest.raises(FrozenInstanceError):
        loaded_config.model_name = "another-model"  # type: ignore[misc]


def test_load_slm_config_uses_process_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overrides = {
        "SLM_BASE_URL": "http://localhost:8000/v1",
        "SLM_MODEL_NAME": "Qwen/Qwen2.5-3B-Instruct",
        "SLM_API_KEY": "test-key",
        "SLM_STRUCTURED_MODE": "json_object",
        "SLM_MAX_PROMPT_CHARS": "50000",
        "SLM_MAX_OUTPUT_TOKENS": "4096",
        "SLM_RUN_MAX_REQUESTS": "20",
        "SLM_RUN_MAX_TOTAL_TOKENS": "200000",
        "SLM_REQUEST_TIMEOUT": "120",
        "SLM_CONTEXT_PROBE": "0",
    }
    for variable_name, value in overrides.items():
        monkeypatch.setenv(variable_name, value)

    loaded_config = load_slm_config()

    assert loaded_config == SLMConfig(
        base_url="http://localhost:8000/v1",
        model_name="Qwen/Qwen2.5-3B-Instruct",
        api_key="test-key",
        structured_mode="json_object",
        max_prompt_chars=50_000,
        max_output_tokens=4_096,
        run_max_requests=20,
        run_max_total_tokens=200_000,
        request_timeout=120,
        context_probe=False,
    )


def test_dotenv_values_take_precedence_over_process_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_path = tmp_path / ".env.slm"
    env_path.write_text(
        "SLM_MODEL_NAME=model-from-file\nSLM_RUN_MAX_REQUESTS=7\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "_SLM_ENV_PATH", env_path)
    monkeypatch.setenv("SLM_MODEL_NAME", "model-from-process")
    monkeypatch.setenv("SLM_RUN_MAX_REQUESTS", "99")

    loaded_config = load_slm_config()

    assert loaded_config.model_name == "model-from-file"
    assert loaded_config.run_max_requests == 7


@pytest.mark.parametrize(
    ("variable_name", "invalid_value"),
    [
        ("SLM_MAX_PROMPT_CHARS", "0"),
        ("SLM_MAX_OUTPUT_TOKENS", "-1"),
        ("SLM_RUN_MAX_REQUESTS", "1.5"),
        ("SLM_RUN_MAX_TOTAL_TOKENS", "many"),
        ("SLM_REQUEST_TIMEOUT", ""),
    ],
)
def test_load_slm_config_rejects_invalid_positive_integers(
    monkeypatch: pytest.MonkeyPatch,
    variable_name: str,
    invalid_value: str,
) -> None:
    monkeypatch.setenv(variable_name, invalid_value)

    with pytest.raises(ValueError, match=variable_name):
        load_slm_config()


def test_load_slm_config_rejects_empty_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLM_BASE_URL", "  ")

    with pytest.raises(ValueError, match="SLM_BASE_URL"):
        load_slm_config()


def test_load_slm_config_rejects_unknown_structured_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLM_STRUCTURED_MODE", "xml")

    with pytest.raises(ValueError, match="SLM_STRUCTURED_MODE"):
        load_slm_config()
