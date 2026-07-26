"""Run-scoped limits for LLM request count and token consumption.

The budget is deliberately independent from any model provider.  A workflow
activates one :class:`RunBudget` for the duration of a run; the centralized LLM
client can then call :func:`reserve_request` immediately before a provider call
and :func:`record_usage` after receiving provider usage metadata.

``ContextVar`` keeps unrelated runs isolated while allowing copied async
contexts belonging to the same run to share the same thread-safe budget
instance.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterator, TypedDict


class RunBudgetExceededError(RuntimeError):
    """Raised before an LLM request that would exceed the active run budget."""

    def __init__(
        self,
        *,
        metric: str,
        limit: int,
        used: int,
        attempted: int,
    ) -> None:
        """Describe the exhausted metric with machine-readable attributes."""
        self.metric = metric
        self.limit = limit
        self.used = used
        self.attempted = attempted
        display_metric = "LLM requests" if metric == "requests" else "total tokens"
        super().__init__(
            "Run budget exceeded before LLM API request: "
            f"{display_metric} would be {attempted}, but the run limit is "
            f"{limit} ({used} already used)."
        )


class RunBudgetSnapshot(TypedDict):
    """JSON-safe immutable-by-copy view of one run's current budget."""

    max_requests: int | None
    max_total_tokens: int | None
    request_count: int
    retry_count: int
    prompt_tokens: int
    output_tokens: int
    total_tokens: int
    remaining_requests: int | None
    remaining_tokens: int | None
    exhausted: bool


def _validate_limit(name: str, value: int | None) -> None:
    """Require a non-negative integer limit, with ``None`` meaning unlimited."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer or None.")
    if value < 0:
        raise ValueError(f"{name} must not be negative.")


def _validate_token_count(name: str, value: int) -> None:
    """Reject malformed provider usage before mutating a run budget."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must not be negative.")


@dataclass(slots=True)
class RunBudget:
    """Thread-safe request and token accounting for one workflow run.

    ``estimated_tokens`` passed to :meth:`reserve_request` provides a strict
    pre-request token gate.  When no reliable estimate is available, the
    already-consumed total is still checked before every request.  Actual
    provider usage is always recorded, even if it is higher than the estimate;
    in that case the next request is rejected and the snapshot preserves the
    true (possibly over-limit) consumption.
    """

    max_requests: int | None
    max_total_tokens: int | None
    _request_count: int = field(default=0, init=False, repr=False)
    _retry_count: int = field(default=0, init=False, repr=False)
    _prompt_tokens: int = field(default=0, init=False, repr=False)
    _output_tokens: int = field(default=0, init=False, repr=False)
    _total_tokens: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate limits once so all subsequent accounting is predictable."""
        _validate_limit("max_requests", self.max_requests)
        _validate_limit("max_total_tokens", self.max_total_tokens)
        if self.max_requests is None and self.max_total_tokens is None:
            raise ValueError("At least one run budget limit must be configured.")

    def reserve_request(self, *, estimated_tokens: int = 0) -> int:
        """Atomically reserve one LLM request before contacting the provider.

        Args:
            estimated_tokens: Optional conservative estimate of this request's
                total token use.  Supplying it lets the token limit be enforced
                before the call rather than only preventing a subsequent call.

        Returns:
            The one-based request number within this run.

        Raises:
            RunBudgetExceededError: If the request count or known/estimated
                cumulative token use would exceed its configured limit.
        """
        _validate_token_count("estimated_tokens", estimated_tokens)
        with self._lock:
            attempted_requests = self._request_count + 1
            if (
                self.max_requests is not None
                and attempted_requests > self.max_requests
            ):
                raise RunBudgetExceededError(
                    metric="requests",
                    limit=self.max_requests,
                    used=self._request_count,
                    attempted=attempted_requests,
                )

            if self.max_total_tokens is not None:
                attempted_tokens = self._total_tokens + estimated_tokens
                tokens_exhausted = self._total_tokens >= self.max_total_tokens
                estimate_exceeds_limit = (
                    estimated_tokens > 0
                    and attempted_tokens > self.max_total_tokens
                )
                if tokens_exhausted or estimate_exceeds_limit:
                    raise RunBudgetExceededError(
                        metric="tokens",
                        limit=self.max_total_tokens,
                        used=self._total_tokens,
                        attempted=attempted_tokens,
                    )

            self._request_count = attempted_requests
            return attempted_requests

    def record_usage(
        self,
        *,
        prompt_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> RunBudgetSnapshot:
        """Record actual usage returned by a completed provider request.

        ``total_tokens`` may exceed ``prompt_tokens + output_tokens`` when a
        provider accounts for reasoning, cached, or other token categories.
        Usage is accounting data, so an unexpectedly large response is retained
        rather than discarded or rewritten to make the budget appear satisfied.
        """
        _validate_token_count("prompt_tokens", prompt_tokens)
        _validate_token_count("output_tokens", output_tokens)
        resolved_total = (
            prompt_tokens + output_tokens
            if total_tokens is None
            else total_tokens
        )
        _validate_token_count("total_tokens", resolved_total)
        if resolved_total < prompt_tokens + output_tokens:
            raise ValueError(
                "total_tokens must be at least prompt_tokens + output_tokens."
            )

        with self._lock:
            self._prompt_tokens += prompt_tokens
            self._output_tokens += output_tokens
            self._total_tokens += resolved_total
            return self._snapshot_unlocked()

    def record_retry(self) -> int:
        """Record one validation or transient-provider retry."""
        with self._lock:
            self._retry_count += 1
            return self._retry_count

    def snapshot(self) -> RunBudgetSnapshot:
        """Return a stable, JSON-safe copy of the current accounting state."""
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> RunBudgetSnapshot:
        """Build a snapshot while the caller holds ``_lock``."""
        remaining_requests = (
            None
            if self.max_requests is None
            else max(self.max_requests - self._request_count, 0)
        )
        remaining_tokens = (
            None
            if self.max_total_tokens is None
            else max(self.max_total_tokens - self._total_tokens, 0)
        )
        request_limit_reached = (
            self.max_requests is not None
            and self._request_count >= self.max_requests
        )
        token_limit_reached = (
            self.max_total_tokens is not None
            and self._total_tokens >= self.max_total_tokens
        )
        return {
            "max_requests": self.max_requests,
            "max_total_tokens": self.max_total_tokens,
            "request_count": self._request_count,
            "retry_count": self._retry_count,
            "prompt_tokens": self._prompt_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens": self._total_tokens,
            "remaining_requests": remaining_requests,
            "remaining_tokens": remaining_tokens,
            "exhausted": request_limit_reached or token_limit_reached,
        }


_ACTIVE_RUN_BUDGET: ContextVar[RunBudget | None] = ContextVar(
    "active_run_budget",
    default=None,
)


def get_active_run_budget() -> RunBudget | None:
    """Return the current run's budget, if budgeting is enabled."""
    return _ACTIVE_RUN_BUDGET.get()


@contextmanager
def activate_run_budget(budget: RunBudget) -> Iterator[RunBudget]:
    """Activate an existing budget and restore the prior context on exit."""
    if not isinstance(budget, RunBudget):
        raise TypeError("budget must be a RunBudget instance.")
    token = _ACTIVE_RUN_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _ACTIVE_RUN_BUDGET.reset(token)


@contextmanager
def run_budget(
    *,
    max_requests: int | None,
    max_total_tokens: int | None,
) -> Iterator[RunBudget]:
    """Create and activate an isolated budget for one workflow run."""
    budget = RunBudget(
        max_requests=max_requests,
        max_total_tokens=max_total_tokens,
    )
    with activate_run_budget(budget):
        yield budget


def reserve_request(*, estimated_tokens: int = 0) -> int | None:
    """Reserve against the active run, or do nothing outside a run context."""
    budget = get_active_run_budget()
    if budget is None:
        return None
    return budget.reserve_request(estimated_tokens=estimated_tokens)


def record_usage(
    *,
    prompt_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int | None = None,
) -> RunBudgetSnapshot | None:
    """Record provider usage on the active run, if one is configured."""
    budget = get_active_run_budget()
    if budget is None:
        return None
    return budget.record_usage(
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def record_retry() -> int | None:
    """Record a retry on the active run, or do nothing outside a run."""
    budget = get_active_run_budget()
    if budget is None:
        return None
    return budget.record_retry()


def snapshot() -> RunBudgetSnapshot | None:
    """Return the active run's snapshot, or ``None`` outside a run context."""
    budget = get_active_run_budget()
    return None if budget is None else budget.snapshot()
