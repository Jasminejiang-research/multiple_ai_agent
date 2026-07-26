"""Tests for provider-independent, run-scoped LLM budgets."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from workflow.run_budget import (
    RunBudget,
    RunBudgetExceededError,
    activate_run_budget,
    get_active_run_budget,
    record_retry,
    record_usage,
    reserve_request,
    run_budget,
    snapshot,
)


def test_request_limit_fails_atomically_before_an_extra_call() -> None:
    """The over-limit request is rejected without incrementing accounting."""
    with run_budget(max_requests=2, max_total_tokens=1_000):
        assert reserve_request() == 1
        assert reserve_request() == 2

        with pytest.raises(
            RunBudgetExceededError,
            match="before LLM API request.*run limit is 2",
        ) as error:
            reserve_request()

        assert error.value.metric == "requests"
        assert error.value.used == 2
        assert error.value.attempted == 3
        assert snapshot()["request_count"] == 2  # type: ignore[index]


def test_estimated_tokens_are_checked_before_request_is_reserved() -> None:
    """A conservative estimate prevents a call that cannot fit the run."""
    with run_budget(max_requests=5, max_total_tokens=100):
        assert reserve_request(estimated_tokens=80) == 1
        record_usage(prompt_tokens=50, output_tokens=30)

        with pytest.raises(RunBudgetExceededError) as error:
            reserve_request(estimated_tokens=21)

        assert error.value.metric == "tokens"
        assert error.value.used == 80
        current = snapshot()
        assert current is not None
        assert current["request_count"] == 1
        assert current["remaining_tokens"] == 20


def test_actual_usage_is_accumulated_and_exhausts_token_budget() -> None:
    """Provider totals, including non-prompt/output tokens, are preserved."""
    with run_budget(max_requests=10, max_total_tokens=100):
        reserve_request()
        first = record_usage(
            prompt_tokens=50,
            output_tokens=20,
            total_tokens=75,
        )
        reserve_request()
        final = record_usage(
            prompt_tokens=15,
            output_tokens=10,
            total_tokens=25,
        )

        assert first is not None
        assert first["total_tokens"] == 75
        assert final is not None
        assert final == {
            "max_requests": 10,
            "max_total_tokens": 100,
            "request_count": 2,
            "retry_count": 0,
            "prompt_tokens": 65,
            "output_tokens": 30,
            "total_tokens": 100,
            "remaining_requests": 8,
            "remaining_tokens": 0,
            "exhausted": True,
        }
        with pytest.raises(RunBudgetExceededError, match="total tokens"):
            reserve_request()


def test_unexpected_response_overage_is_visible_and_blocks_next_call() -> None:
    """Actual usage is never hidden when a response exceeds its estimate."""
    with run_budget(max_requests=5, max_total_tokens=100):
        reserve_request(estimated_tokens=90)
        current = record_usage(total_tokens=110)

        assert current is not None
        assert current["total_tokens"] == 110
        assert current["remaining_tokens"] == 0
        assert current["exhausted"] is True
        with pytest.raises(RunBudgetExceededError) as error:
            reserve_request()
        assert error.value.used == 110


def test_contexts_are_isolated_and_restore_the_outer_budget() -> None:
    """Nested runs do not leak counters and the previous context is restored."""
    outer = RunBudget(max_requests=3, max_total_tokens=300)
    inner = RunBudget(max_requests=1, max_total_tokens=50)

    assert get_active_run_budget() is None
    with activate_run_budget(outer):
        reserve_request()
        with activate_run_budget(inner):
            reserve_request()
            record_usage(total_tokens=50)
            assert snapshot()["max_requests"] == 1  # type: ignore[index]
        assert get_active_run_budget() is outer
        assert snapshot()["request_count"] == 1  # type: ignore[index]

    assert get_active_run_budget() is None
    assert snapshot() is None


def test_module_functions_are_noops_without_an_active_run() -> None:
    """Direct LLMClient use remains backward-compatible outside workflows."""
    assert reserve_request(estimated_tokens=999) is None
    assert record_retry() is None
    assert record_usage(prompt_tokens=1, output_tokens=2) is None
    assert snapshot() is None


def test_retry_counter_is_run_scoped() -> None:
    with run_budget(max_requests=2, max_total_tokens=100):
        assert record_retry() == 1
        assert snapshot()["retry_count"] == 1  # type: ignore[index]


def test_one_budget_is_safe_for_parallel_nodes_in_the_same_run() -> None:
    """Parallel callers cannot reserve more requests than the shared limit."""
    budget = RunBudget(max_requests=4, max_total_tokens=1_000)

    def try_reserve() -> bool:
        with activate_run_budget(budget):
            try:
                reserve_request()
            except RunBudgetExceededError:
                return False
            return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: try_reserve(), range(16)))

    assert results.count(True) == 4
    assert results.count(False) == 12
    assert budget.snapshot()["request_count"] == 4


@pytest.mark.parametrize(
    ("factory", "error_type", "message"),
    [
        (
            lambda: RunBudget(max_requests=-1, max_total_tokens=10),
            ValueError,
            "max_requests must not be negative",
        ),
        (
            lambda: RunBudget(max_requests=True, max_total_tokens=10),
            TypeError,
            "max_requests must be an integer",
        ),
        (
            lambda: RunBudget(max_requests=None, max_total_tokens=None),
            ValueError,
            "At least one run budget limit",
        ),
    ],
)
def test_invalid_budget_configuration_fails_fast(
    factory: object,
    error_type: type[Exception],
    message: str,
) -> None:
    """Malformed limits are rejected before a workflow can make API calls."""
    with pytest.raises(error_type, match=message):
        factory()  # type: ignore[operator]


def test_invalid_usage_does_not_partially_mutate_budget() -> None:
    """All usage fields are validated before any counter changes."""
    budget = RunBudget(max_requests=2, max_total_tokens=100)
    budget.reserve_request()

    with pytest.raises(ValueError, match="at least"):
        budget.record_usage(
            prompt_tokens=60,
            output_tokens=30,
            total_tokens=80,
        )

    assert budget.snapshot()["total_tokens"] == 0
