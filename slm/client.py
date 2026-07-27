"""OpenAI-compatible client skeleton for the isolated SLM experiment."""

from __future__ import annotations

try:
    import openai
except ModuleNotFoundError as exc:
    _OPENAI_IMPORT_ERROR = exc

    class _MissingOpenAI:
        """Keep the isolated package importable until SLM extras are installed."""

        @staticmethod
        def OpenAI(**_kwargs):
            raise ModuleNotFoundError(
                "The SLM client requires the optional dependencies from "
                "slm/requirements-slm.txt."
            ) from _OPENAI_IMPORT_ERROR

    openai = _MissingOpenAI()

from slm.config import SLMConfig
from workflow.gemini_schema import relaxed_response_schema
from workflow.llm_client import (
    PromptBudgetExceededError,
    StructuredOutputValidationError,
    _ACTIVE_USAGE_TRACKER,
    _provider_status_code,
    schema_cardinality_contract,
)
from workflow.run_budget import (
    record_retry as record_run_retry,
    record_usage as record_run_usage,
    reserve_request as reserve_run_request,
)


class SLMClient:
    """Hold the OpenAI-compatible SDK client and SLM-only configuration.

    Request construction, response parsing, accounting, and validation are
    intentionally deferred to the subsequent S2.4 and S2.5 tasks.
    """

    def __init__(self, config: SLMConfig) -> None:
        """Initialize an OpenAI-compatible client from validated SLM settings."""
        self._client = openai.OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.request_timeout,
        )
        self._model_name = config.model_name
        self._structured_mode = config.structured_mode
        self._max_prompt_chars = config.max_prompt_chars
        self._max_output_tokens = config.max_output_tokens
