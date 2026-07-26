"""Tests for centralized structured-output correction and usage accounting."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Annotated, Any

from pydantic import BaseModel, Field

from workflow.llm_client import (
    LLMClient,
    PromptBudgetExceededError,
    StructuredJsonLLM,
    StructuredOutputValidationError,
    capture_llm_usage,
    schema_cardinality_contract,
)
from workflow.run_budget import run_budget, snapshot


class LimitedOutput(BaseModel):
    """Small strict schema that reproduces a real list-cardinality failure."""

    items: Annotated[list[str], Field(min_length=1, max_length=2)]


def _response(payload: dict[str, Any]) -> SimpleNamespace:
    """Return a Gemini-like response with deterministic usage metadata."""
    return SimpleNamespace(
        text=json.dumps(payload),
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=5,
            total_token_count=15,
        ),
    )


class FakeModels:
    """Return responses or raise provider errors in configured order."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeGeminiClient:
    """Expose the ``models`` surface used by ``LLMClient``."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.models = FakeModels(outcomes)


def _client(outcomes: list[Any], *, max_prompt_chars: int = 20_000) -> LLMClient:
    """Create an LLMClient whose network surface is replaced by a fake."""
    client = LLMClient(
        api_key="test-key",
        max_prompt_chars=max_prompt_chars,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
    )
    client._client = FakeGeminiClient(outcomes)  # type: ignore[assignment]
    return client


class LLMClientTests(unittest.TestCase):
    """Exercise behavior at the same validation layer used in production."""

    def test_first_validation_failure_retries_once_then_succeeds(self) -> None:
        """An over-limit first response gets exactly one corrected API request."""
        client = _client(
            [
                _response({"items": ["one", "two", "three"]}),
                _response({"items": ["one", "two"]}),
            ]
        )
        adapter = StructuredJsonLLM(client, LimitedOutput)

        with capture_llm_usage() as usage:
            result = adapter.generate_json("Return the requested JSON.")

        self.assertEqual(LimitedOutput.model_validate_json(result).items, ["one", "two"])
        self.assertEqual(len(client._client.models.calls), 2)  # type: ignore[attr-defined]
        correction_prompt = client._client.models.calls[1]["contents"]  # type: ignore[attr-defined]
        self.assertIn("# Structured Output Correction", correction_prompt)
        self.assertIn("at most 2 items", correction_prompt)
        self.assertIn("do not silently truncate", correction_prompt)
        self.assertEqual(usage.request_count, 2)
        self.assertEqual(usage.retry_count, 1)
        self.assertEqual(usage.total_tokens, 30)
        self.assertGreater(usage.approximate_cost, 0)

    def test_persistent_validation_failure_stops_after_two_calls(self) -> None:
        """A second invalid response is returned as an error without a third call."""
        client = _client(
            [
                _response({"items": ["one", "two", "three"]}),
                _response({"items": ["one", "two", "three"]}),
            ]
        )

        with self.assertRaises(StructuredOutputValidationError):
            client.generate_structured("Return JSON.", LimitedOutput)

        self.assertEqual(len(client._client.models.calls), 2)  # type: ignore[attr-defined]

    def test_semantic_validation_uses_the_same_single_retry_budget(self) -> None:
        """A dynamic source/citation error is fed back once, then corrected."""
        client = _client(
            [
                _response({"items": ["uncited"]}),
                _response({"items": ["cited"]}),
            ]
        )
        adapter = StructuredJsonLLM(client, LimitedOutput)

        def require_citation_marker(output: BaseModel) -> None:
            validated = LimitedOutput.model_validate(output)
            if "cited" not in validated.items:
                raise ValueError(
                    "proposal claim lacks exact inline [source-id] citation"
                )

        result = adapter.generate_json_validated(
            "Return the requested JSON.",
            require_citation_marker,
        )

        self.assertEqual(LimitedOutput.model_validate_json(result).items, ["cited"])
        self.assertEqual(len(client._client.models.calls), 2)  # type: ignore[attr-defined]
        correction_prompt = client._client.models.calls[1]["contents"]  # type: ignore[attr-defined]
        self.assertIn("lacks exact inline [source-id] citation", correction_prompt)
        self.assertIn("only correction attempt", correction_prompt)

    def test_persistent_semantic_failure_stops_after_two_calls(self) -> None:
        """Repeated source/citation failure never causes a third request."""
        client = _client(
            [
                _response({"items": ["uncited"]}),
                _response({"items": ["still-uncited"]}),
            ]
        )

        def reject_output(output: LimitedOutput) -> None:
            raise ValueError("unknown source ID")

        with self.assertRaisesRegex(
            StructuredOutputValidationError,
            "unknown source ID",
        ):
            client.generate_structured(
                "Return JSON.",
                LimitedOutput,
                output_validator=reject_output,
            )

        self.assertEqual(len(client._client.models.calls), 2)  # type: ignore[attr-defined]

    def test_provider_quota_error_is_not_retried(self) -> None:
        """Provider/configuration failures such as HTTP 429 consume one request."""
        client = _client([RuntimeError("429 RESOURCE_EXHAUSTED")])

        with self.assertRaisesRegex(RuntimeError, "429"):
            client.generate_structured("Return JSON.", LimitedOutput)

        self.assertEqual(len(client._client.models.calls), 1)  # type: ignore[attr-defined]

    def test_provider_503_retries_once_then_succeeds(self) -> None:
        """Only service-unavailable errors receive one short transport retry."""
        client = _client(
            [
                RuntimeError("503 UNAVAILABLE"),
                _response({"items": ["one"]}),
            ]
        )

        with capture_llm_usage() as usage:
            with run_budget(max_requests=3, max_total_tokens=100_000):
                result = client.generate_structured_once(
                    "Return JSON.",
                    LimitedOutput,
                )
                budget = snapshot()

        self.assertEqual(result.items, ["one"])
        self.assertEqual(len(client._client.models.calls), 2)  # type: ignore[attr-defined]
        self.assertEqual(usage.request_count, 2)
        self.assertEqual(usage.retry_count, 1)
        self.assertIsNotNone(budget)
        self.assertEqual(budget["request_count"], 2)  # type: ignore[index]
        self.assertEqual(budget["retry_count"], 1)  # type: ignore[index]

    def test_provider_auth_and_rate_errors_never_retry(self) -> None:
        """401, 403, and 429 bypass structure and transport correction."""
        for status in (401, 403, 429):
            with self.subTest(status=status):
                client = _client([RuntimeError(f"{status} provider error")])
                with self.assertRaisesRegex(RuntimeError, str(status)):
                    client.generate_structured("Return JSON.", LimitedOutput)
                self.assertEqual(
                    len(client._client.models.calls),  # type: ignore[attr-defined]
                    1,
                )

    def test_generate_structured_once_does_not_schema_retry(self) -> None:
        """Revision can reserve its second call for a failed-section patch."""
        client = _client(
            [_response({"items": ["one", "two", "three"]})]
        )

        with self.assertRaises(StructuredOutputValidationError):
            client.generate_structured_once("Return JSON.", LimitedOutput)

        self.assertEqual(len(client._client.models.calls), 1)  # type: ignore[attr-defined]

    def test_prompt_budget_fails_before_api_request(self) -> None:
        """An oversized prompt is rejected locally without consuming quota."""
        client = _client([_response({"items": ["one"]})], max_prompt_chars=40)

        with self.assertRaises(PromptBudgetExceededError):
            client.generate_structured("x" * 41, LimitedOutput)

        self.assertEqual(len(client._client.models.calls), 0)  # type: ignore[attr-defined]

    def test_schema_contract_is_generated_from_pydantic_limits(self) -> None:
        """List bounds are derived from the strict schema, not copied by hand."""
        contract = schema_cardinality_contract(LimitedOutput)

        self.assertIn("`items`: 1 to 2 items", contract)
        self.assertIn("Merge duplicate or closely related entries", contract)


if __name__ == "__main__":
    unittest.main()
