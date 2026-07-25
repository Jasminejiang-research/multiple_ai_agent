"""Tavily provider client for the controlled web search interface."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from pydantic import ValidationError

from schemas import WebSearchResult
from tools.recency import to_tavily_time_range
from tools.source_quality import classify_source_quality

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class WebSearchProviderError(RuntimeError):
    """Base error raised when a real web search provider call fails."""


class WebSearchConfigurationError(WebSearchProviderError):
    """Raised when the Tavily provider is not configured."""


class WebSearchRateLimitError(WebSearchProviderError):
    """Raised when Tavily rejects a request because its rate limit was reached."""


class _HttpClient(Protocol):
    """Minimal HTTP client contract required by ``TavilySearchClient``."""

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        timeout: float,
    ) -> requests.Response:
        """Send an HTTP POST request and return its response."""


class TavilySearchClient:
    """Call Tavily Search and normalize its response into project schemas."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 15.0,
        http_client: _HttpClient | None = None,
    ) -> None:
        """Initialize the provider with a key, timeout, and injectable HTTP client."""
        normalized_key = api_key.strip()
        if not normalized_key:
            raise WebSearchConfigurationError(
                "TAVILY_API_KEY is not set. Add it to the environment or .env."
            )
        if timeout <= 0:
            raise ValueError("timeout must be positive.")

        self._api_key = normalized_key
        self._timeout = timeout
        self._http_client = http_client or requests.Session()

    @classmethod
    def from_environment(cls) -> TavilySearchClient:
        """Create a client from ``TAVILY_API_KEY`` in the environment or .env."""
        load_dotenv()
        return cls(api_key=os.getenv("TAVILY_API_KEY", ""))

    def search(
        self,
        query: str,
        allowed_domains: list[str] | None,
        recency: str | None,
        max_results: int,
    ) -> list[WebSearchResult]:
        """Search Tavily and return normalized, schema-validated results."""
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        if allowed_domains:
            payload["include_domains"] = allowed_domains
        if recency:
            time_range = to_tavily_time_range(recency)
            if time_range is not None:
                payload["time_range"] = time_range

        try:
            response = self._http_client.post(
                TAVILY_SEARCH_URL,
                json=payload,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise WebSearchProviderError("Tavily search timed out.") from exc
        except requests.RequestException as exc:
            raise WebSearchProviderError(
                "Tavily search could not be completed."
            ) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_hint = (
                f" Retry after {retry_after} seconds." if retry_after else ""
            )
            raise WebSearchRateLimitError(
                f"Tavily search rate limit reached.{retry_hint}"
            )

        if response.status_code >= 400:
            raise WebSearchProviderError(
                f"Tavily search failed with HTTP {response.status_code}."
            )

        try:
            response_data = response.json()
        except requests.JSONDecodeError as exc:
            raise WebSearchProviderError(
                "Tavily returned an invalid JSON response."
            ) from exc

        if not isinstance(response_data, Mapping):
            raise WebSearchProviderError(
                "Tavily returned an unexpected response structure."
            )
        if response_data.get("error"):
            raise WebSearchProviderError("Tavily returned a search API error.")

        raw_results = response_data.get("results") or []
        if not isinstance(raw_results, list):
            raise WebSearchProviderError(
                "Tavily returned an unexpected results structure."
            )

        try:
            return [
                self._normalize_result(result)
                for result in raw_results[:max_results]
            ]
        except (TypeError, ValidationError, ValueError) as exc:
            raise WebSearchProviderError(
                "Tavily returned an invalid search result."
            ) from exc

    @staticmethod
    def _normalize_result(result: object) -> WebSearchResult:
        """Convert one Tavily result object to ``WebSearchResult``."""
        if not isinstance(result, Mapping):
            raise TypeError("Tavily result must be an object.")

        url = str(result.get("url") or "")
        publisher = result.get("publisher")
        if not publisher:
            publisher = urlsplit(url).hostname

        return WebSearchResult(
            title=str(result.get("title") or ""),
            url=url,
            publisher=str(publisher) if publisher else None,
            published_date=(
                str(result["published_date"])
                if result.get("published_date")
                else None
            ),
            summary=str(result.get("content") or result.get("summary") or ""),
            relevance_score=float(result.get("score", 0.0)),
            source_quality=classify_source_quality(
                url,
                str(publisher) if publisher else None,
            ),
        )
