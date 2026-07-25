"""Tests for the controlled web search tool interface."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from schemas import SourceQuality, WebSearchResult
from tools import web_search
from tools.tavily_search import (
    TAVILY_SEARCH_URL,
    TavilySearchClient,
    WebSearchConfigurationError,
    WebSearchProviderError,
    WebSearchRateLimitError,
)


class FakeResponse:
    """Small requests-compatible response used by provider unit tests."""

    def __init__(
        self,
        status_code: int,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Store the status, JSON payload, and optional response headers."""
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> object:
        """Return the configured fake JSON payload."""
        return self._payload


class FakeHttpClient:
    """Capture Tavily request data and return a configured response."""

    def __init__(self, response: FakeResponse) -> None:
        """Initialize the fake with the response returned by ``post``."""
        self.response = response
        self.call: dict[str, object] = {}

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        """Capture one HTTP call without accessing the network."""
        self.call = {"url": url, "json": json, "timeout": timeout}
        return self.response


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each search should leave an auditable query and timestamp."""
    monkeypatch.setattr(web_search, "_search_provider", lambda *args: [])

    with caplog.at_level(logging.INFO, logger=web_search.__name__):
        assert web_search.search_web("market trends") == []

    record = caplog.records[-1]
    assert record.web_search_query == "market trends"
    logged_at = datetime.fromisoformat(record.web_search_timestamp)
    assert logged_at.tzinfo is not None
    assert logged_at.utcoffset() is not None


def test_search_web_keeps_and_marks_stale_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local recency enforcement annotates old results without dropping them."""
    monkeypatch.setattr(
        web_search,
        "_search_provider",
        lambda *args: [
            {
                "title": "Historical report",
                "url": "https://example.com/historical",
                "published_date": "2000-01-01",
                "summary": "Older but still relevant background.",
                "relevance_score": 0.75,
            },
            {
                "title": "Future-dated report",
                "url": "https://example.com/current",
                "published_date": "2999-01-01",
                "summary": "A result inside the requested date window.",
                "relevance_score": 0.7,
            },
        ],
    )

    results = web_search.search_web("market history", recency="last_12_months")

    assert len(results) == 2
    assert [result.stale for result in results] == [True, False]


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        ({"query": "  "}, ValueError),
        ({"query": "market", "allowed_domains": [""]}, ValueError),
        ({"query": "market", "recency": " "}, ValueError),
        ({"query": "market", "recency": "whenever"}, ValueError),
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


def test_tavily_client_normalizes_results_and_forwards_controls() -> None:
    """Tavily fields and controls map to the controlled project interface."""
    http_client = FakeHttpClient(
        FakeResponse(
            200,
            {
                "results": [
                    {
                        "title": "EU AI market report",
                        "url": "https://research.example/report",
                        "content": "A concise provider result.",
                        "score": 0.87,
                        "published_date": "2026-07-01",
                    }
                ]
            },
        )
    )
    client = TavilySearchClient(
        "secret-key",
        timeout=7.5,
        http_client=http_client,
    )

    results = client.search(
        "European AI market",
        ["research.example"],
        "last_12_months",
        3,
    )

    assert http_client.call["url"] == TAVILY_SEARCH_URL
    assert http_client.call["timeout"] == 7.5
    payload = http_client.call["json"]
    assert isinstance(payload, dict)
    assert payload["api_key"] == "secret-key"
    assert payload["include_domains"] == ["research.example"]
    assert payload["time_range"] == "year"
    assert payload["max_results"] == 3
    assert results == [
        WebSearchResult(
            title="EU AI market report",
            url="https://research.example/report",
            publisher="research.example",
            published_date="2026-07-01",
            summary="A concise provider result.",
            relevance_score=0.87,
            source_quality=SourceQuality.RESEARCH_ORG,
        )
    ]


def test_tavily_client_returns_empty_list_for_no_results() -> None:
    """A successful provider response with no matches is not an error."""
    client = TavilySearchClient(
        "secret-key",
        http_client=FakeHttpClient(FakeResponse(200, {"results": []})),
    )

    assert client.search("niche query", None, None, 5) == []


def test_tavily_client_raises_explicit_rate_limit_error() -> None:
    """HTTP 429 is distinguishable from other provider failures."""
    client = TavilySearchClient(
        "secret-key",
        http_client=FakeHttpClient(
            FakeResponse(429, {}, headers={"Retry-After": "30"})
        ),
    )

    with pytest.raises(WebSearchRateLimitError, match="30 seconds"):
        client.search("market", None, None, 5)


@pytest.mark.parametrize("status_code", [400, 401, 500, 503])
def test_tavily_client_handles_api_errors(status_code: int) -> None:
    """Non-rate-limit HTTP failures produce a readable provider error."""
    client = TavilySearchClient(
        "secret-key",
        http_client=FakeHttpClient(FakeResponse(status_code, {})),
    )

    with pytest.raises(WebSearchProviderError, match=str(status_code)):
        client.search("market", None, None, 5)


def test_tavily_client_requires_api_key() -> None:
    """Production configuration fails clearly when its API key is absent."""
    with pytest.raises(WebSearchConfigurationError, match="TAVILY_API_KEY"):
        TavilySearchClient("  ")
