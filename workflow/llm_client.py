"""Single Gemini entry point shared by every workflow node and agent.

Architecture rule (enforced since the Phase 3 ``additional_properties`` 400):
no workflow node or agent may build its own ``genai.Client`` or
``GenerateContentConfig``. Everything goes through ``LLMClient.generate_structured``
so schema-compatibility fixes (see ``workflow.gemini_schema``) live in exactly
one place.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from workflow.gemini_schema import relaxed_response_schema
from workflow.run_budget import (
    record_retry as record_run_retry,
    record_usage as record_run_usage,
    reserve_request as reserve_run_request,
)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"
DEFAULT_MAX_PROMPT_CHARS = 120_000
DEFAULT_MAX_OUTPUT_TOKENS = 16_384
MAX_VALIDATION_FEEDBACK_CHARS = 4_000
TRANSIENT_RETRY_DELAY_SECONDS = 0.25

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredOutputValidationError(ValueError):
    """A retryable failure caused by empty or schema-invalid model output."""


class PromptBudgetExceededError(ValueError):
    """A non-retryable failure raised before an over-budget API request."""


@dataclass
class LLMUsageTracker:
    """Usage accumulated by LLM calls made inside one logged workflow node."""

    request_count: int = 0
    retry_count: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    approximate_cost: float = 0.0

    def as_dict(self) -> dict[str, int | float]:
        """Return a JSON-safe snapshot for run-history persistence."""
        return {
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "approximate_cost": round(self.approximate_cost, 8),
        }


_ACTIVE_USAGE_TRACKER: ContextVar[LLMUsageTracker | None] = ContextVar(
    "active_llm_usage_tracker",
    default=None,
)


@contextmanager
def capture_llm_usage() -> Iterator[LLMUsageTracker]:
    """Collect request, retry, token, and estimated-cost data in this context."""
    tracker = LLMUsageTracker()
    token = _ACTIVE_USAGE_TRACKER.set(tracker)
    try:
        yield tracker
    finally:
        _ACTIVE_USAGE_TRACKER.reset(token)


def _non_negative_float_env(name: str) -> float:
    """Read an optional non-negative float configuration value."""
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return 0.0
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if value < 0:
        raise ValueError(f"{name} must not be negative.")
    return value


def _positive_int_env(name: str, default: int) -> int:
    """Read an optional positive integer configuration value."""
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive.")
    return value


def _provider_status_code(exc: Exception) -> int | None:
    """Best-effort HTTP status extraction across Gemini exception variants."""
    for attribute_name in ("status_code", "code"):
        value = getattr(exc, attribute_name, None)
        if callable(value):
            try:
                value = value()
            except TypeError:
                value = None
        enum_value = getattr(value, "value", value)
        if isinstance(enum_value, int):
            return enum_value
        if isinstance(enum_value, str) and enum_value.isdigit():
            return int(enum_value)
    match = re.search(r"(?<!\d)(401|403|429|503)(?!\d)", str(exc))
    return int(match.group(1)) if match else None


def _validation_feedback(exc: Exception) -> str:
    """Preserve complete structured failure reports when one is available."""
    current: BaseException | None = exc
    for _ in range(4):
        feedback_builder = getattr(current, "validation_feedback", None)
        if callable(feedback_builder):
            feedback = feedback_builder()
            if isinstance(feedback, str) and feedback:
                return feedback
        current = current.__cause__
        if current is None:
            break
    return str(exc)[:MAX_VALIDATION_FEEDBACK_CHARS]


def _resolve_local_ref(
    root_schema: Mapping[str, Any],
    reference: str,
) -> Mapping[str, Any] | None:
    """Resolve a local JSON Schema reference such as ``#/$defs/Model``."""
    if not reference.startswith("#/"):
        return None
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, Mapping) else None


def _collect_array_limits(
    fragment: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: tuple[str, ...],
    output: list[tuple[str, int | None, int | None]],
    *,
    depth: int = 0,
) -> None:
    """Collect nested ``minItems``/``maxItems`` constraints with field paths."""
    if depth > 16:
        return

    reference = fragment.get("$ref")
    if isinstance(reference, str):
        resolved = _resolve_local_ref(root_schema, reference)
        if resolved is not None:
            _collect_array_limits(
                resolved,
                root_schema,
                path,
                output,
                depth=depth + 1,
            )
        return

    minimum = fragment.get("minItems")
    maximum = fragment.get("maxItems")
    if path and (isinstance(minimum, int) or isinstance(maximum, int)):
        output.append(
            (
                ".".join(path),
                minimum if isinstance(minimum, int) else None,
                maximum if isinstance(maximum, int) else None,
            )
        )

    items = fragment.get("items")
    if isinstance(items, Mapping):
        item_path = (
            (*path[:-1], f"{path[-1]}[]")
            if path
            else ("[]",)
        )
        _collect_array_limits(
            items,
            root_schema,
            item_path,
            output,
            depth=depth + 1,
        )

    properties = fragment.get("properties")
    if isinstance(properties, Mapping):
        for field_name, field_schema in properties.items():
            if isinstance(field_schema, Mapping):
                _collect_array_limits(
                    field_schema,
                    root_schema,
                    (*path, str(field_name)),
                    output,
                    depth=depth + 1,
                )

    for union_key in ("anyOf", "oneOf", "allOf"):
        alternatives = fragment.get(union_key)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, Mapping):
                    _collect_array_limits(
                        alternative,
                        root_schema,
                        path,
                        output,
                        depth=depth + 1,
                    )


def schema_cardinality_contract(schema: type[BaseModel]) -> str:
    """Generate compact list-size instructions from a strict Pydantic schema."""
    root_schema = schema.model_json_schema()
    limits: list[tuple[str, int | None, int | None]] = []
    _collect_array_limits(root_schema, root_schema, (), limits)

    unique_limits = sorted(set(limits))
    grouped: defaultdict[
        tuple[str, int | None, int | None],
        list[str],
    ] = defaultdict(list)
    for path, minimum, maximum in unique_limits:
        leaf = path.rsplit(".", 1)[-1]
        grouped[(leaf, minimum, maximum)].append(path)

    instructions: list[str] = []
    emitted: set[tuple[str, int | None, int | None]] = set()
    for path, minimum, maximum in unique_limits:
        leaf = path.rsplit(".", 1)[-1]
        group_key = (leaf, minimum, maximum)
        grouped_paths = grouped[group_key]
        if len(grouped_paths) >= 3:
            if group_key in emitted:
                continue
            emitted.add(group_key)
            display_path = f"*.{leaf} ({len(grouped_paths)} fields)"
        else:
            display_path = path

        if minimum is not None and maximum is not None and minimum == maximum:
            rule = f"exactly {minimum} items"
        elif minimum is not None and maximum is not None:
            rule = f"{minimum} to {maximum} items"
        elif minimum is not None:
            rule = f"at least {minimum} items"
        else:
            rule = f"at most {maximum} items"
        instructions.append(f"- `{display_path}`: {rule}.")

    if not instructions:
        return ""
    return (
        "# Schema List-Size Contract (generated automatically)\n\n"
        + "\n".join(instructions)
        + "\n\nMerge duplicate or closely related entries to satisfy maximums. "
        "Do not silently truncate or remove essential dependencies."
    )


class LLMClient:
    """The only object in this codebase allowed to talk to the Gemini API."""

    def __init__(
        self,
        api_key: str,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        max_prompt_chars: int | None = None,
        max_output_tokens: int | None = None,
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
    ) -> None:
        """Initialize the shared Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name
        self._max_prompt_chars = (
            max_prompt_chars
            if max_prompt_chars is not None
            else _positive_int_env(
                "LLM_MAX_PROMPT_CHARS",
                DEFAULT_MAX_PROMPT_CHARS,
            )
        )
        if self._max_prompt_chars < 1:
            raise ValueError("max_prompt_chars must be positive.")
        self._max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else _positive_int_env(
                "LLM_MAX_OUTPUT_TOKENS_PER_REQUEST",
                DEFAULT_MAX_OUTPUT_TOKENS,
            )
        )
        if self._max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive.")
        self._input_cost_per_million = (
            input_cost_per_million
            if input_cost_per_million is not None
            else _non_negative_float_env(
                "GEMINI_INPUT_USD_PER_MILLION_TOKENS"
            )
        )
        self._output_cost_per_million = (
            output_cost_per_million
            if output_cost_per_million is not None
            else _non_negative_float_env(
                "GEMINI_OUTPUT_USD_PER_MILLION_TOKENS"
            )
        )
        if self._input_cost_per_million < 0 or self._output_cost_per_million < 0:
            raise ValueError("Token cost rates must not be negative.")

    def _check_prompt_budget(self, prompt: str) -> None:
        """Reject an oversized prompt before it consumes API quota."""
        if len(prompt) > self._max_prompt_chars:
            raise PromptBudgetExceededError(
                "LLM prompt exceeds the configured character budget "
                f"({len(prompt)} > {self._max_prompt_chars}); reduce evidence "
                "or critique input before retrying."
            )

    def _record_response_usage(self, response: Any) -> None:
        """Add Gemini usage metadata to node and run-scoped accounting."""
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_token_count", prompt_tokens + output_tokens)
            or prompt_tokens + output_tokens
        )
        tracker = _ACTIVE_USAGE_TRACKER.get()
        if tracker is not None:
            tracker.prompt_tokens += prompt_tokens
            tracker.output_tokens += output_tokens
            tracker.total_tokens += total_tokens
            tracker.approximate_cost += (
                prompt_tokens * self._input_cost_per_million
                + output_tokens * self._output_cost_per_million
            ) / 1_000_000
        record_run_usage(
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    def _generate_once(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float,
        system_instruction: str | None,
        output_validator: Callable[[ModelT], None] | None,
    ) -> ModelT:
        """Make one API request and run schema plus optional semantic validation."""
        self._check_prompt_budget(prompt)
        response: Any | None = None
        estimated_prompt_tokens = max(1, (len(prompt) + 3) // 4)
        for attempt in range(2):
            reserve_run_request(
                estimated_tokens=(
                    estimated_prompt_tokens + self._max_output_tokens
                )
            )
            tracker = _ACTIVE_USAGE_TRACKER.get()
            if tracker is not None:
                tracker.request_count += 1
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=relaxed_response_schema(schema),
                        temperature=temperature,
                        max_output_tokens=self._max_output_tokens,
                    ),
                )
                break
            except Exception as exc:
                if attempt == 0 and _provider_status_code(exc) == 503:
                    if tracker is not None:
                        tracker.retry_count += 1
                    record_run_retry()
                    time.sleep(TRANSIENT_RETRY_DELAY_SECONDS)
                    continue
                raise
        if response is None:  # pragma: no cover - defensive loop invariant
            raise RuntimeError("Gemini request did not produce a response.")
        self._record_response_usage(response)

        if not response.text:
            raise StructuredOutputValidationError(
                f"Gemini returned an empty response for {schema.__name__}."
            )

        try:
            result = schema.model_validate_json(response.text)
        except ValidationError as exc:
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

    def generate_structured(
        self,
        prompt: str,
        schema: type[ModelT],
        *,
        temperature: float = 0.2,
        system_instruction: str | None = None,
        output_validator: Callable[[ModelT], None] | None = None,
    ) -> ModelT:
        """Generate output constrained to ``schema`` and strictly validate it.

        Gemini receives the relaxed (constraint-stripped, ref-inlined,
        ``additionalProperties``-free) variant of the schema so the request is
        always accepted; the raw response text is then validated against the
        strict Pydantic model before being returned.

        Args:
            prompt: Full prompt text for the model.
            schema: Strict Pydantic model describing the desired output.
            temperature: Sampling temperature for this call.
            system_instruction: Optional system instruction for the call.
            output_validator: Optional dynamic semantic validator. A
                ``ValueError`` from this validator shares the same single
                correction attempt as Pydantic schema validation.

        Returns:
            A validated instance of ``schema``.

        Exactly one correction request is made when the first response is empty
        or fails strict Pydantic validation. Configuration, prompt-budget,
        authentication, permission, quota/rate-limit, and network failures are
        not caught and therefore never trigger a correction request.

        Raises:
            StructuredOutputValidationError: If both outputs fail validation.
            PromptBudgetExceededError: If either prompt exceeds its budget.
        """
        constrained_prompt = self._constrained_prompt(prompt, schema)
        try:
            return self._generate_once(
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
            return self._generate_once(
                correction_prompt,
                schema,
                temperature=temperature,
                system_instruction=system_instruction,
                output_validator=output_validator,
            )

    @staticmethod
    def _constrained_prompt(prompt: str, schema: type[BaseModel]) -> str:
        """Append Pydantic-derived list limits to one model prompt."""
        cardinality_contract = schema_cardinality_contract(schema)
        return (
            f"{prompt}\n\n{cardinality_contract}"
            if cardinality_contract
            else prompt
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
        """Make one semantic generation attempt with no schema-correction call.

        Provider HTTP 503 handling remains transport-level and is limited to
        the single short retry implemented by :meth:`_generate_once`.
        """
        return self._generate_once(
            self._constrained_prompt(prompt, schema),
            schema,
            temperature=temperature,
            system_instruction=system_instruction,
            output_validator=output_validator,
        )


class StructuredJsonLLM:
    """Adapter binding ``LLMClient`` to one schema behind ``generate_json``.

    Existing nodes and agents depend on small ``generate_json(prompt) -> str``
    protocols (easy to fake in tests). This adapter keeps those call sites and
    tests unchanged while routing every real call through the shared client.
    """

    def __init__(
        self,
        client: LLMClient,
        schema: type[BaseModel],
        *,
        temperature: float = 0.2,
    ) -> None:
        """Bind a shared client to one output schema and temperature."""
        self._client = client
        self._schema = schema
        self._temperature = temperature

    def generate_json(self, prompt: str) -> str:
        """Return validated JSON text matching the bound schema."""
        result = self._client.generate_structured(
            prompt,
            self._schema,
            temperature=self._temperature,
        )
        return result.model_dump_json()

    def generate_json_validated(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None],
    ) -> str:
        """Return JSON after schema and caller-supplied semantic validation."""
        result = self._client.generate_structured(
            prompt,
            self._schema,
            temperature=self._temperature,
            output_validator=output_validator,
        )
        return result.model_dump_json()

    def generate_json_once(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None] | None = None,
    ) -> str:
        """Return one bound-schema attempt without automatic correction."""
        result = self._client.generate_structured_once(
            prompt,
            self._schema,
            temperature=self._temperature,
            output_validator=output_validator,
        )
        return result.model_dump_json()

    def generate_json_for_schema_once(
        self,
        prompt: str,
        schema: type[BaseModel],
        output_validator: Callable[[BaseModel], None] | None = None,
    ) -> str:
        """Return one attempt for an alternate schema such as a section patch."""
        result = self._client.generate_structured_once(
            prompt,
            schema,
            temperature=self._temperature,
            output_validator=output_validator,
        )
        return result.model_dump_json()


def create_default_llm_client() -> LLMClient:
    """Create the production ``LLMClient`` from environment configuration."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", DEFAULT_MODEL_NAME)
    return LLMClient(api_key=api_key, model_name=model_name)
