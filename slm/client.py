"""OpenAI-compatible client for the isolated SLM experiment."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

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

from slm.config import SLMConfig, SLM_FORCE_JSON_OBJECT_SCHEMAS
from workflow.gemini_schema import relaxed_response_schema
from workflow.llm_client import (
    PromptBudgetExceededError,
    StructuredOutputValidationError,
    _ACTIVE_USAGE_TRACKER,
    _provider_status_code,
    _validation_feedback,
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
        structured_mode = (
            "json_object"
            if schema.__name__ in SLM_FORCE_JSON_OBJECT_SCHEMAS
            else self._structured_mode
        )
        if structured_mode == "json_schema":
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
        if structured_mode == "json_object":
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

    @staticmethod
    def _extract_json_text(text: str) -> str:
        """Remove code fences and prose surrounding one JSON object."""
        stripped_text = text.strip()
        object_start = stripped_text.find("{")
        object_end = stripped_text.rfind("}")
        if object_start != -1 and object_end >= object_start:
            return stripped_text[object_start : object_end + 1]
        return stripped_text

    def _record_response_usage(self, response: Any) -> None:
        """Add OpenAI-compatible usage metadata to shared accounting."""
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(
                usage,
                "total_tokens",
                prompt_tokens + output_tokens,
            )
            or prompt_tokens + output_tokens
        )

        tracker = _ACTIVE_USAGE_TRACKER.get()
        if tracker is not None:
            tracker.prompt_tokens += prompt_tokens
            tracker.output_tokens += output_tokens
            tracker.total_tokens += total_tokens
            # Local SLM inference has no metered provider cost.
            tracker.approximate_cost += 0.0

        record_run_usage(
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    def _validate_response(
        self,
        response: Any,
        schema: type[ModelT],
        *,
        output_validator: Callable[[ModelT], None] | None,
    ) -> ModelT:
        """Record usage, extract JSON, and apply strict output validation."""
        self._record_response_usage(response)

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            content = None
        if not isinstance(content, str) or not content.strip():
            raise StructuredOutputValidationError(
                f"SLM returned an empty response for {schema.__name__}."
            )

        json_text = self._extract_json_text(content)
        try:
            result = schema.model_validate_json(json_text)
        except (ValidationError, ValueError) as exc:
            raise StructuredOutputValidationError(
                f"Invalid {schema.__name__} output: {exc}"
            ) from exc

        if output_validator is not None:
            try:
                output_validator(result)
            except ValueError as exc:
                raise StructuredOutputValidationError(
                    f"Invalid {schema.__name__} output: {exc}"
                ) from exc
        return result

    def _generate_validated_once(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float,
        system_instruction: str | None,
        output_validator: Callable[[ModelT], None] | None,
    ) -> ModelT:
        """Make one request and validate its OpenAI-compatible response."""
        response = self._generate_once(
            prompt,
            schema,
            temperature=temperature,
            system_instruction=system_instruction,
        )
        return self._validate_response(
            response,
            schema,
            output_validator=output_validator,
        )

    @staticmethod
    def _constrained_prompt(
        prompt: str,
        schema: type[BaseModel],
    ) -> str:
        """Append Pydantic-derived list limits to one model prompt."""
        cardinality_contract = schema_cardinality_contract(schema)
        return (
            f"{prompt}\n\n{cardinality_contract}"
            if cardinality_contract
            else prompt
        )

    def generate_structured(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        system_instruction: str | None = None,
        output_validator: Callable[[ModelT], None] | None = None,
    ) -> ModelT:
        """Generate strictly validated output with one correction attempt."""
        constrained_prompt = self._constrained_prompt(prompt, schema)
        try:
            return self._generate_validated_once(
                constrained_prompt,
                schema,
                temperature=temperature,
                system_instruction=system_instruction,
                output_validator=output_validator,
            )
        except StructuredOutputValidationError as exc:
            tracker = _ACTIVE_USAGE_TRACKER.get()
            if tracker is not None:
                tracker.retry_count += 1
            record_run_retry()
            feedback = _validation_feedback(exc)
            correction_prompt = (
                f"{constrained_prompt}\n\n"
                "# Structured Output Correction\n\n"
                f"The previous {schema.__name__} output failed strict validation:\n"
                f"{feedback}\n\n"
                "This is the only correction attempt. Return the complete corrected "
                "JSON object only. Merge duplicate or closely related list entries "
                "to satisfy the generated limits; do not silently truncate them."
            )
            return self._generate_validated_once(
                correction_prompt,
                schema,
                temperature=temperature,
                system_instruction=system_instruction,
                output_validator=output_validator,
            )

    def generate_structured_once(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        system_instruction: str | None = None,
        output_validator: Callable[[ModelT], None] | None = None,
    ) -> ModelT:
        """Generate and validate exactly once, without schema correction."""
        return self._generate_validated_once(
            self._constrained_prompt(prompt, schema),
            schema,
            temperature=temperature,
            system_instruction=system_instruction,
            output_validator=output_validator,
        )
