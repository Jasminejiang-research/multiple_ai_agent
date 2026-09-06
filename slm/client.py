"""OpenAI-compatible client for the isolated SLM experiment."""

from __future__ import annotations

import json
import threading
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
from slm.schema_contract import schema_enum_contract
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

# The SDK timeout is an httpx read timeout, which measures the gap between
# socket reads rather than total elapsed time. It is not a wall-clock bound: one
# observed request ran 10h21m against SLM_REQUEST_TIMEOUT=2700 before the server
# returned 500. This multiplier gives the SDK timeout first chance to raise a
# proper APITimeoutError; the watchdog below only catches the case where it
# never fires at all.
WALL_CLOCK_GRACE_MULTIPLIER = 1.2

ModelT = TypeVar("ModelT", bound=BaseModel)


class SLMRequestDeadlineExceeded(TimeoutError):
    """Raised when a request outlives its wall-clock deadline."""


def _call_with_deadline(
    call: Callable[[], Any],
    deadline_seconds: float,
    *,
    description: str,
) -> Any:
    """Run ``call`` on a daemon thread and abandon it past ``deadline_seconds``.

    Python cannot kill a thread, so an abandoned request keeps its socket until
    the server answers. That is acceptable: the deadline is only reached when
    the run is failing anyway, and the thread is a daemon so it can never hold
    up interpreter exit -- which is exactly what turned one stuck request into
    an overnight hang.
    """
    outcome: list[Any] = []
    failure: list[BaseException] = []
    finished = threading.Event()

    def run() -> None:
        try:
            outcome.append(call())
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller
            failure.append(exc)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True, name="slm-request").start()

    if not finished.wait(deadline_seconds):
        raise SLMRequestDeadlineExceeded(
            f"{description} exceeded its {deadline_seconds:.0f}s wall-clock "
            "deadline without the transport timing out. The request was "
            "abandoned; raise SLM_REQUEST_TIMEOUT only if the endpoint is "
            "genuinely this slow."
        )
    if failure:
        raise failure[0]
    return outcome[0]


class SLMClient:
    """Send schema-constrained requests through an OpenAI-compatible endpoint."""

    def __init__(self, config: SLMConfig) -> None:
        """Initialize an OpenAI-compatible client from validated SLM settings."""
        # ``max_retries=0`` is mandatory, not a tuning choice. The SDK default
        # of 2 retries each failed request *inside* one ``create()`` call, so a
        # timeout costs three times ``SLM_REQUEST_TIMEOUT`` of wall time and the
        # extra attempts bypass ``reserve_run_request`` and the usage tracker
        # entirely. Transient errors are retried below, where they are counted.
        self._client = openai.OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.request_timeout,
            max_retries=0,
        )
        self._model_name = config.model_name
        self._structured_mode = config.structured_mode
        self._max_prompt_chars = config.max_prompt_chars
        self._request_deadline = (
            config.request_timeout * WALL_CLOCK_GRACE_MULTIPLIER
        )
        self._input_cost_per_million = config.input_cost_per_million_tokens
        self._output_cost_per_million = config.output_cost_per_million_tokens
        self._max_output_tokens = config.max_output_tokens

    def measure_context_window(self, probe_tokens: int) -> int:
        """Return the server's effective context window, in tokens.

        A serving stack that cannot fit ``probe_tokens`` truncates the prompt
        and then reports its own window as ``usage.prompt_tokens``; a stack that
        can fit them reports the probe size back. Either way the returned value
        is the ground truth measured at the endpoint rather than an assumption
        about server configuration.

        The probe deliberately bypasses the prompt budget, the usage tracker,
        and run accounting: it runs during preflight, outside any run.
        """
        if probe_tokens < 1:
            raise ValueError("probe_tokens must be positive.")

        # "token " tokenizes to one token per repetition on Qwen-family BPE
        # vocabularies (measured ratio 1.01), so the probe size is predictable.
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": "token " * probe_tokens}],
            temperature=0,
            max_tokens=1,
        )
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        if prompt_tokens < 1:
            raise RuntimeError(
                "SLM endpoint did not report prompt_tokens, so the context "
                "window cannot be verified."
            )
        return prompt_tokens

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
        structured_mode = (
            "json_object"
            if schema.__name__ in SLM_FORCE_JSON_OBJECT_SCHEMAS
            else self._structured_mode
        )
        if structured_mode == "json_schema":
            # Relaxation exists for constrained decoders that compile the schema
            # into a state machine, so it only applies on this path.
            return (
                prompt,
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": relaxed_response_schema(schema),
                    },
                },
            )
        if structured_mode == "json_object":
            # Here the schema is only prompt text: nothing compiles it, so the
            # strict schema is what the model should see. It carries the enum
            # members and length bounds that the relaxed variant drops -- the
            # model was inventing claim_type values it had never been shown --
            # and it is also *smaller*, because $ref avoids inlining repeated
            # definitions. Strict Pydantic validation is unchanged either way.
            schema_text = json.dumps(schema.model_json_schema())
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
                return _call_with_deadline(
                    lambda: self._client.chat.completions.create(
                        model=self._model_name,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=self._max_output_tokens,
                        response_format=response_format,
                    ),
                    self._request_deadline,
                    description=f"SLM {schema.__name__} request",
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
            # Zero for a local endpoint, and configurable so a hosted one (the
            # DashScope arm) does not silently report a cost of zero.
            tracker.approximate_cost += (
                prompt_tokens * self._input_cost_per_million
                + output_tokens * self._output_cost_per_million
            ) / 1_000_000

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
            choice = response.choices[0]
            content = choice.message.content
        except (AttributeError, IndexError, TypeError):
            choice = None
            content = None
        if not isinstance(content, str) or not content.strip():
            raise StructuredOutputValidationError(
                f"SLM returned an empty response for {schema.__name__}."
            )

        # Without this, hitting the token cap surfaces as "Invalid JSON: EOF
        # while parsing", which points at the parser instead of at the length
        # limit. Raising here still spends the one correction attempt, and the
        # feedback tells the model what actually went wrong.
        if getattr(choice, "finish_reason", None) == "length":
            raise StructuredOutputValidationError(
                f"{schema.__name__} output was cut off at the "
                f"{self._max_output_tokens}-token limit "
                "(finish_reason='length'), so the JSON is incomplete. Return a "
                "shorter response: keep every required field but make each "
                "string concise, and never repeat a phrase or punctuation to "
                "fill space."
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
        """Append Pydantic-derived list limits and enum members to one prompt.

        The list-size contract is the shared one used by the Gemini arm. The
        enum contract is SLM-only: a 3B model invents enum values that describe
        the surrounding field even with the members present in the schema.
        """
        contracts = [
            contract
            for contract in (
                schema_cardinality_contract(schema),
                schema_enum_contract(schema),
            )
            if contract
        ]
        if not contracts:
            return prompt
        return prompt + "\n\n" + "\n\n".join(contracts)

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
