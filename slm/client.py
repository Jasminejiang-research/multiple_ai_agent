"""OpenAI-compatible client for the isolated SLM experiment."""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

from pydantic import BaseModel

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

TRANSIENT_RETRY_DELAY_SECONDS = 0.25
_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503})

ModelT = TypeVar("ModelT", bound=BaseModel)


class SLMClient:
    """Send schema-constrained requests through an OpenAI-compatible endpoint."""

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

    def _check_prompt_budget(self, prompt: str) -> None:
        """Reject an oversized final request prompt before any reservation."""
        if len(prompt) > self._max_prompt_chars:
            raise PromptBudgetExceededError(
                "SLM prompt exceeds the configured character budget "
                f"({len(prompt)} > {self._max_prompt_chars}); reduce evidence "
                "or critique input before retrying."
            )

    def _request_prompt_and_format(
        self,
        prompt: str,
        schema: type[BaseModel],
    ) -> tuple[str, dict[str, Any]]:
        """Build the provider prompt and response format for the selected mode."""
        response_schema = relaxed_response_schema(schema)
        if self._structured_mode == "json_schema":
            return (
                prompt,
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": response_schema,
                    },
                },
            )
        if self._structured_mode == "json_object":
            schema_text = json.dumps(response_schema)
            return (
                f"{prompt}\n\n"
                "# Output JSON Schema (must match exactly)\n\n"
                f"{schema_text}",
                {"type": "json_object"},
            )
        raise ValueError(
            "SLM structured mode must be 'json_schema' or 'json_object'; "
            f"got {self._structured_mode!r}."
        )

    def _generate_once(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        system_instruction: str | None = None,
    ) -> Any:
        """Make one structured request, with one short transient-error retry."""
        request_prompt, response_format = self._request_prompt_and_format(
            prompt,
            schema,
        )
        self._check_prompt_budget(request_prompt)

        messages: list[dict[str, str]] = []
        if system_instruction is not None:
            messages.append(
                {"role": "system", "content": system_instruction}
            )
        messages.append({"role": "user", "content": request_prompt})

        estimated_tokens = (
            len(request_prompt) // 4 + self._max_output_tokens
        )
        tracker = _ACTIVE_USAGE_TRACKER.get()
        for attempt in range(2):
            reserve_run_request(estimated_tokens=estimated_tokens)
            if tracker is not None:
                tracker.request_count += 1
            try:
                return self._client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=self._max_output_tokens,
                    response_format=response_format,
                )
            except Exception as exc:
                if (
                    attempt == 0
                    and _provider_status_code(exc)
                    in _TRANSIENT_STATUS_CODES
                ):
                    if tracker is not None:
                        tracker.retry_count += 1
                    record_run_retry()
                    time.sleep(TRANSIENT_RETRY_DELAY_SECONDS)
                    continue
                raise

        raise RuntimeError("SLM request did not produce a response.")
