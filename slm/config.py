"""Configuration loading for the isolated SLM experiment."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.siliconflow.com/v1"
DEFAULT_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
# No usable default: a hosted endpoint rejects a placeholder, and failing at the
# first request with an auth error is clearer than defaulting to something that
# looks configured. Set SLM_API_KEY in slm/.env.slm.
DEFAULT_API_KEY = ""
DEFAULT_STRUCTURED_MODE = "json_object"
DEFAULT_MAX_PROMPT_CHARS = 60_000
DEFAULT_MAX_OUTPUT_TOKENS = 8_192
DEFAULT_RUN_MAX_REQUESTS = 12
DEFAULT_RUN_MAX_TOTAL_TOKENS = 160_000
# One Finance request measured 281s end to end on the reference CPU machine;
# 300s left no margin for the larger writer and section-writer requests.
DEFAULT_REQUEST_TIMEOUT = 900
DEFAULT_CONTEXT_PROBE = True
# Zero suits a local endpoint. A hosted endpoint must set these, or the SLM arm
# reports a cost of zero in every run record and Phase 7 compares against it.
DEFAULT_INPUT_COST_PER_MILLION_TOKENS = 0.0
DEFAULT_OUTPUT_COST_PER_MILLION_TOKENS = 0.0
# Off by default: chunking changes how the SLM arm writes relative to the
# Gemini arm (one request for all 13 sections), which is a Phase 7
# comparability decision rather than a default.
DEFAULT_CHUNKED_WRITER = False
# Off by default for the same comparability reason: pruned schemas ask the
# model for less than the Gemini arm produces. See slm/pruning.py.
DEFAULT_PRUNED_SCHEMAS = False

# Measured on qwen2.5:3b for this workload (prompt + appended JSON schema):
# 9,700 chars -> 2,227 tokens = 4.36 chars/token. The conservative 4.0 used
# here over-estimates the token requirement, which is the safe direction.
CHARS_PER_TOKEN = 4.0

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
    context_probe: bool = DEFAULT_CONTEXT_PROBE
    chunked_writer: bool = DEFAULT_CHUNKED_WRITER
    pruned_schemas: bool = DEFAULT_PRUNED_SCHEMAS
    input_cost_per_million_tokens: float = DEFAULT_INPUT_COST_PER_MILLION_TOKENS
    output_cost_per_million_tokens: float = DEFAULT_OUTPUT_COST_PER_MILLION_TOKENS


def required_context_tokens(config: SLMConfig) -> int:
    """Return the smallest server context window this configuration needs.

    A serving stack whose window is smaller than this silently truncates the
    prompt instead of failing, which strips the instruction header out of every
    request. ``slm.preflight_slm`` turns that into a startup error.
    """
    prompt_tokens = math.ceil(config.max_prompt_chars / CHARS_PER_TOKEN)
    return prompt_tokens + config.max_output_tokens


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


def _non_negative_float(variable_name: str, default: float) -> float:
    raw_value = _environment_value(variable_name, str(default))
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{variable_name} must be a non-negative number; got {raw_value!r}."
        ) from exc
    if value < 0:
        raise ValueError(
            f"{variable_name} must be a non-negative number; got {raw_value!r}."
        )
    return value


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _boolean_value(variable_name: str, default: bool) -> bool:
    raw_value = _environment_value(variable_name, "1" if default else "0")
    value = raw_value.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{variable_name} must be a boolean flag such as 1/0; got {raw_value!r}."
    )


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
        context_probe=_boolean_value(
            "SLM_CONTEXT_PROBE",
            DEFAULT_CONTEXT_PROBE,
        ),
        chunked_writer=_boolean_value(
            "SLM_CHUNKED_WRITER",
            DEFAULT_CHUNKED_WRITER,
        ),
        pruned_schemas=_boolean_value(
            "SLM_PRUNED_SCHEMAS",
            DEFAULT_PRUNED_SCHEMAS,
        ),
        input_cost_per_million_tokens=_non_negative_float(
            "SLM_INPUT_USD_PER_MILLION_TOKENS",
            DEFAULT_INPUT_COST_PER_MILLION_TOKENS,
        ),
        output_cost_per_million_tokens=_non_negative_float(
            "SLM_OUTPUT_USD_PER_MILLION_TOKENS",
            DEFAULT_OUTPUT_COST_PER_MILLION_TOKENS,
        ),
    )
