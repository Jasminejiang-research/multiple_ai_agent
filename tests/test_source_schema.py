"""Tests for controlled web research source schemas."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from schemas import SourceQuality, WebSearchResult


def test_source_quality_contains_the_architecture_categories() -> None:
    """The enum must match the controlled web search quality vocabulary."""
    assert {quality.value for quality in SourceQuality} == {
        "official",
        "financial_report",
        "research_org",
        "news",
        "blog",
        "unknown",
    }


def test_web_search_result_accepts_and_normalizes_all_fields() -> None:
    """A complete architecture-shaped result should validate and serialize."""
    result = WebSearchResult(
        title="  Annual Report  ",
        url="https://example.com/report",
        publisher="  Example Corp  ",
        published_date="2026-07-24",
        summary="  Audited annual results.  ",
        relevance_score=0.82,
        source_quality="financial_report",
    )

    assert result.title == "Annual Report"
    assert result.publisher == "Example Corp"
    assert result.summary == "Audited annual results."
    assert result.source_quality is SourceQuality.FINANCIAL_REPORT
    assert result.model_dump(mode="json") == {
        "title": "Annual Report",
        "url": "https://example.com/report",
        "publisher": "Example Corp",
        "published_date": "2026-07-24",
        "summary": "Audited annual results.",
        "relevance_score": 0.82,
        "source_quality": "financial_report",
        "stale": False,
    }


def test_web_search_result_supports_missing_source_metadata() -> None:
    """Unavailable publisher and publication date remain explicit null fields."""
    result = WebSearchResult(
        title="Search result",
        url="https://example.com/result",
        summary="Relevant source summary.",
        relevance_score=0.5,
    )

    assert result.publisher is None
    assert result.published_date is None
    assert result.source_quality is SourceQuality.UNKNOWN
    assert result.stale is False


def test_web_search_result_parses_human_and_iso_datetimes() -> None:
    """Provider publication dates are normalized to calendar dates."""
    human_date = WebSearchResult(
        title="Research note",
        url="https://example.com/research",
        published_date="July 24, 2026",
        summary="Relevant source summary.",
        relevance_score=0.5,
    )
    iso_datetime = WebSearchResult(
        title="News item",
        url="https://example.com/news",
        published_date="2026-07-24T18:30:00Z",
        summary="Relevant source summary.",
        relevance_score=0.5,
    )

    assert human_date.published_date == date(2026, 7, 24)
    assert iso_datetime.published_date == date(2026, 7, 24)


def test_web_search_result_rejects_unparseable_published_date() -> None:
    """Invalid provider dates must not silently become misleading metadata."""
    with pytest.raises(ValidationError, match="recognizable calendar date"):
        WebSearchResult(
            title="Research note",
            url="https://example.com/research",
            published_date="not a date",
            summary="Relevant source summary.",
            relevance_score=0.5,
        )


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_web_search_result_rejects_out_of_range_relevance(score: float) -> None:
    """Relevance scores outside the normalized 0-1 range are invalid."""
    with pytest.raises(ValidationError):
        WebSearchResult(
            title="Search result",
            url="https://example.com/result",
            summary="Relevant source summary.",
            relevance_score=score,
        )
