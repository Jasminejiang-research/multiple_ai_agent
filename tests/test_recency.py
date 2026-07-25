"""Tests for deterministic source recency handling."""

from __future__ import annotations

from datetime import date

import pytest

from schemas import WebSearchResult
from tools.recency import mark_stale_sources, parse_recency, to_tavily_time_range


def _result(title: str, published_date: str | None) -> WebSearchResult:
    return WebSearchResult(
        title=title,
        url=f"https://example.com/{title.lower()}",
        published_date=published_date,
        summary="Relevant source summary.",
        relevance_score=0.8,
    )


def test_last_12_months_marks_old_source_without_deleting_it() -> None:
    """Sources before the cutoff remain in the result list and become stale."""
    results = mark_stale_sources(
        [
            _result("Current", "2025-07-25"),
            _result("Stale", "2025-07-24"),
            _result("Undated", None),
        ],
        "last_12_months",
        as_of=date(2026, 7, 25),
    )

    assert [result.title for result in results] == [
        "Current",
        "Stale",
        "Undated",
    ]
    assert [result.stale for result in results] == [False, True, False]


@pytest.mark.parametrize(
    ("value", "amount", "unit"),
    [
        ("last_12_months", 12, "months"),
        ("30d", 30, "days"),
        ("week", 1, "weeks"),
    ],
)
def test_parse_recency_supports_named_compact_and_provider_values(
    value: str,
    amount: int,
    unit: str,
) -> None:
    """Public recency formats map to explicit calendar windows."""
    window = parse_recency(value)

    assert (window.amount, window.unit) == (amount, unit)


def test_parse_recency_rejects_unknown_values() -> None:
    """Unknown controls fail locally instead of reaching the provider."""
    with pytest.raises(ValueError, match="Unsupported recency"):
        parse_recency("whenever")


def test_last_12_months_maps_to_tavily_year_filter() -> None:
    """The local twelve-month control uses Tavily's equivalent coarse filter."""
    assert to_tavily_time_range("last_12_months") == "year"
