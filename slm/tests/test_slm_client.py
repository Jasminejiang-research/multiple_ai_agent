"""Tests for OpenAI-compatible SLM request construction and accounting."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

import workflow.llm_client as shared_llm_client
from workflow.llm_client import (
    PromptBudgetExceededError,
    StructuredOutputValidationError,
    capture_llm_usage,
)
from workflow.run_budget import run_budget

import slm.client as client_module
from slm.client import SLMClient
from slm.config import SLMConfig
from workflow.gemini_schema import relaxed_response_schema


class ExampleOutput(BaseModel):
    answer: str


class ProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"provider error {status_code}")
        self.status_code = status_code


class FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeOpenAI:
    def __init__(self, outcomes: list[Any]) -> None:
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


def _config(
    *,
    structured_mode: str = "json_schema",
    max_prompt_chars: int = 60_000,
    max_output_tokens: int = 32,
) -> SLMConfig:
    return SLMConfig(
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:3b",
        api_key="ollama",
        structured_mode=structured_mode,
        max_prompt_chars=max_prompt_chars,
        max_output_tokens=max_output_tokens,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=300,
    )


def _client_with_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[Any],
    **config_overrides: Any,
) -> tuple[SLMClient, FakeCompletions]:
    fake_openai = FakeOpenAI(outcomes)
    monkeypatch.setattr(
        client_module.openai,
        "OpenAI",
        lambda **_kwargs: object(),
    )
    client = SLMClient(_config(**config_overrides))
    client._client = fake_openai
    return client, fake_openai.completions


def test_slm_client_initializes_openai_compatible_sdk(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sdk_client = object()

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return sdk_client

    monkeypatch.setattr(client_module.openai, "OpenAI", fake_openai)

    client = SLMClient(_config())

    assert captured == {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "timeout": 300,
    }
    assert client._client is sdk_client
    assert client._model_name == "qwen2.5:3b"
    assert client._structured_mode == "json_schema"
    assert client._max_prompt_chars == 60_000
    assert client._max_output_tokens == 32


def test_json_schema_mode_builds_expected_request(monkeypatch) -> None:
    response = object()
    client, completions = _client_with_outcomes(monkeypatch, [response])

    result = client._generate_once(
        "Give one answer.",
        ExampleOutput,
        temperature=0.4,
        system_instruction="Be concise.",
    )

    assert result is response
    assert completions.calls == [
        {
            "model": "qwen2.5:3b",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Give one answer."},
            ],
            "temperature": 0.4,
            "max_tokens": 32,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "ExampleOutput",
                    "schema": relaxed_response_schema(ExampleOutput),
                },
            },
        }
    ]


def test_json_object_mode_appends_schema_to_user_prompt(monkeypatch) -> None:
    response = object()
    client, completions = _client_with_outcomes(
        monkeypatch,
        [response],
        structured_mode="json_object",
    )

    client._generate_once("Give one answer.", ExampleOutput)

    call = completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0]["role"] == "user"
    request_prompt = call["messages"][0]["content"]
    assert request_prompt.startswith(
        "Give one answer.\n\n"
        "# Output JSON Schema (must match exactly)\n\n"
    )
    assert '"answer"' in request_prompt


def test_prompt_budget_is_checked_before_reservation_or_api_call(
    monkeypatch,
) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [object()],
        max_prompt_chars=5,
    )

    with capture_llm_usage() as usage, run_budget(
        max_requests=2,
        max_total_tokens=1_000,
    ) as budget:
        with pytest.raises(PromptBudgetExceededError):
            client._generate_once("too long", ExampleOutput)

    assert completions.calls == []
    assert usage.request_count == 0
    assert budget.snapshot()["request_count"] == 0


@pytest.mark.parametrize("status_code", [429, 500, 502, 503])
def test_transient_error_retries_once_and_updates_accounting(
    monkeypatch,
    status_code: int,
) -> None:
    response = object()
    client, completions = _client_with_outcomes(
        monkeypatch,
        [ProviderError(status_code), response],
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(client_module.time, "sleep", sleep_calls.append)

    with capture_llm_usage() as usage, run_budget(
        max_requests=3,
        max_total_tokens=1_000,
    ) as budget:
        result = client._generate_once("answer", ExampleOutput)

    assert result is response
    assert len(completions.calls) == 2
    assert sleep_calls == [0.25]
    assert usage.request_count == 2
    assert usage.retry_count == 1
    assert budget.snapshot()["request_count"] == 2
    assert budget.snapshot()["retry_count"] == 1


def test_non_transient_error_is_not_retried(monkeypatch) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [ProviderError(401)],
    )
    monkeypatch.setattr(
        client_module.time,
        "sleep",
        lambda _seconds: pytest.fail("unexpected retry sleep"),
    )

    with pytest.raises(ProviderError):
        client._generate_once("answer", ExampleOutput)

    assert len(completions.calls) == 1


def test_first_validation_failure_gets_one_correction_then_succeeds(
    monkeypatch,
) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [
            _response("{}"),
            _response('{"answer": "corrected"}'),
        ],
    )

    with capture_llm_usage() as usage:
        result = client.generate_structured("Give one answer.", ExampleOutput)

    assert result == ExampleOutput(answer="corrected")
    assert len(completions.calls) == 2
    correction_prompt = completions.calls[1]["messages"][-1]["content"]
    assert "# Structured Output Correction" in correction_prompt
    assert "This is the only correction attempt." in correction_prompt
    assert usage.request_count == 2
    assert usage.retry_count == 1
    assert usage.prompt_tokens == 20
    assert usage.output_tokens == 10
    assert usage.total_tokens == 30
    assert usage.approximate_cost == 0.0


def test_two_validation_failures_raise_after_exactly_two_calls(
    monkeypatch,
) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [_response("{}"), _response("{}")],
    )

    with pytest.raises(StructuredOutputValidationError):
        client.generate_structured("Give one answer.", ExampleOutput)

    assert len(completions.calls) == 2


def test_json_code_fence_and_surrounding_text_are_parsed(monkeypatch) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [
            _response(
                "Here is the result:\n"
                "```json\n"
                '{"answer": "inside fence"}\n'
                "```\n"
                "Done."
            )
        ],
    )

    result = client.generate_structured_once(
        "Give one answer.",
        ExampleOutput,
    )

    assert result == ExampleOutput(answer="inside fence")
    assert len(completions.calls) == 1


def test_usage_tokens_aggregate_and_decrement_run_budget(monkeypatch) -> None:
    client, completions = _client_with_outcomes(
        monkeypatch,
        [_response('{"answer": "accounted"}')],
    )

    with capture_llm_usage() as usage, run_budget(
        max_requests=2,
        max_total_tokens=1_000,
    ) as budget:
        result = client.generate_structured_once(
            "Give one answer.",
            ExampleOutput,
        )
        budget_snapshot = budget.snapshot()

    assert result == ExampleOutput(answer="accounted")
    assert len(completions.calls) == 1
    assert usage.request_count == 1
    assert usage.retry_count == 0
    assert usage.prompt_tokens == 10
    assert usage.output_tokens == 5
    assert usage.total_tokens == 15
    assert usage.approximate_cost == 0.0
    assert budget_snapshot["request_count"] == 1
    assert budget_snapshot["retry_count"] == 0
    assert budget_snapshot["prompt_tokens"] == 10
    assert budget_snapshot["output_tokens"] == 5
    assert budget_snapshot["total_tokens"] == 15
    assert budget_snapshot["remaining_requests"] == 1
    assert budget_snapshot["remaining_tokens"] == 985


def test_shared_usage_tracker_private_contract() -> None:
    assert hasattr(shared_llm_client, "_ACTIVE_USAGE_TRACKER")
    assert (
        client_module._ACTIVE_USAGE_TRACKER
        is shared_llm_client._ACTIVE_USAGE_TRACKER
    )
