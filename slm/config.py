"""Configuration loading for the isolated SLM experiment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL_NAME = "qwen2.5:3b"
DEFAULT_API_KEY = "ollama"
DEFAULT_STRUCTURED_MODE = "json_object"
DEFAULT_MAX_PROMPT_CHARS = 60_000
DEFAULT_MAX_OUTPUT_TOKENS = 8_192
DEFAULT_RUN_MAX_REQUESTS = 12
DEFAULT_RUN_MAX_TOTAL_TOKENS = 160_000
DEFAULT_REQUEST_TIMEOUT = 300

_SLM_ENV_PATH = Path(__file__).resolve().with_name(".env.slm")
_SUPPORTED_STRUCTURED_MODES = frozenset({"json_object", "json_schema"})
SLM_FORCE_JSON_OBJECT_SCHEMAS = frozenset(
    {
        "SectionDrafts",
        "ProposalDraft",
        "RevisedProposal",
    }
)


@dataclass(frozen=True, slots=True)
class SLMConfig:
    """Validated settings used only by the isolated SLM integration."""

    base_url: str
    model_name: str
    api_key: str
    structured_mode: str
    max_prompt_chars: int
    max_output_tokens: int
    run_max_requests: int
    run_max_total_tokens: int
    request_timeout: int


def _environment_value(variable_name: str, default: str) -> str:
    value = os.getenv(variable_name)
    return default if value is None else value


def _positive_integer(variable_name: str, default: int) -> int:
    raw_value = _environment_value(variable_name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{variable_name} must be a positive integer; got {raw_value!r}."
        ) from exc
    if value < 1:
        raise ValueError(
            f"{variable_name} must be a positive integer; got {raw_value!r}."
        )
    return value


def _non_empty_value(variable_name: str, default: str) -> str:
    value = _environment_value(variable_name, default).strip()
    if not value:
        raise ValueError(f"{variable_name} must be non-empty.")
    return value


def _structured_mode() -> str:
    variable_name = "SLM_STRUCTURED_MODE"
    value = _environment_value(variable_name, DEFAULT_STRUCTURED_MODE).strip()
    if value not in _SUPPORTED_STRUCTURED_MODES:
        allowed_modes = ", ".join(sorted(_SUPPORTED_STRUCTURED_MODES))
        raise ValueError(
            f"{variable_name} must be one of {allowed_modes}; got {value!r}."
        )
    return value


def load_slm_config() -> SLMConfig:
    """Load and validate SLM-only settings.

    Values in ``slm/.env.slm`` take precedence. When that file is absent or a
    key is omitted, the process environment and then the documented defaults
    are used.
    """

    load_dotenv(dotenv_path=_SLM_ENV_PATH, override=True)

    return SLMConfig(
        base_url=_non_empty_value("SLM_BASE_URL", DEFAULT_BASE_URL),
        model_name=_environment_value("SLM_MODEL_NAME", DEFAULT_MODEL_NAME),
        api_key=_environment_value("SLM_API_KEY", DEFAULT_API_KEY),
        structured_mode=_structured_mode(),
        max_prompt_chars=_positive_integer(
            "SLM_MAX_PROMPT_CHARS",
            DEFAULT_MAX_PROMPT_CHARS,
        ),
        max_output_tokens=_positive_integer(
            "SLM_MAX_OUTPUT_TOKENS",
            DEFAULT_MAX_OUTPUT_TOKENS,
        ),
        run_max_requests=_positive_integer(
            "SLM_RUN_MAX_REQUESTS",
            DEFAULT_RUN_MAX_REQUESTS,
        ),
        run_max_total_tokens=_positive_integer(
            "SLM_RUN_MAX_TOTAL_TOKENS",
            DEFAULT_RUN_MAX_TOTAL_TOKENS,
        ),
        request_timeout=_positive_integer(
            "SLM_REQUEST_TIMEOUT",
            DEFAULT_REQUEST_TIMEOUT,
        ),
    )
