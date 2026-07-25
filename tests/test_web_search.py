"""Tests for the controlled web search tool interface."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from schemas import SourceQuality, WebSearchResult
from tools import web_search


def test_search_web_uses_mock_provider_and_returns_typed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The interface forwards controls and normalizes provider output."""
    provider_call: dict[str, object] = {}

    def mock_provider(
        query: str,
        allowed_domains: list[str] | None,
        recency: str | None,
        max_results: int,
    ) -> list[dict[str, object]]:
        provider_call.update(
            query=query,
            allowed_domains=allowed_domains,
            recency=recency,
            max_results=max_results,
        )
        return [
            {
                "title": "Example research",
                "url": "https://example.com/research",
                "publisher": "Example Institute",
                "published_date": "2026-07-24",
                "summary": "A relevant research summary.",
                "relevance_score": 0.9,
                "source_quality": "research_org",
            }
        ]

    monkeypatch.setattr(web_search, "_search_provider", mock_provider)

    results = web_search.search_web(
        "  European AI market  ",
        allowed_domains=[" Example.COM "],
        recency=" 30d ",
        max_results=3,
    )

    assert provider_call == {
        "query": "European AI market",
        "allowed_domains": ["example.com"],
        "recency": "30d",
        "max_results": 3,
    }
    assert len(results) == 1
    assert isinstance(results[0], WebSearchResult)
    assert results[0].source_quality is SourceQuality.RESEARCH_ORG


def test_search_web_records_query_and_utc_timestamp(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each mock search should leave an auditable query and timestamp."""
    with caplog.at_level(logging.INFO, logger=web_search.__name__):
        assert web_search.search_web("market trends") == []

    record = caplog.records[-1]
    assert record.web_search_query == "market trends"
    logged_at = datetime.fromisoformat(record.web_search_timestamp)
    assert logged_at.tzinfo is not None
    assert logged_at.utcoffset() is not None


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        ({"query": "  "}, ValueError),
        ({"query": "market", "allowed_domains": [""]}, ValueError),
        ({"query": "market", "recency": " "}, ValueError),
        ({"query": "market", "max_results": 0}, ValueError),
    ],
)
def test_search_web_rejects_invalid_controls(
    kwargs: dict[str, object],
    error_type: type[Exception],
) -> None:
    """Invalid search controls must fail before a provider is called."""
    with pytest.raises(error_type):
        web_search.search_web(**kwargs)
