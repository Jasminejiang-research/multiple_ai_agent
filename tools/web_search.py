"""Controlled, provider-agnostic web search interface."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, TypeAlias

from schemas import WebSearchResult

logger = logging.getLogger(__name__)

SearchResultInput: TypeAlias = WebSearchResult | Mapping[str, Any]
SearchProvider: TypeAlias = Callable[
    [str, list[str] | None, str | None, int],
    Sequence[SearchResultInput],
]


def _mock_search_provider(
    query: str,
    allowed_domains: list[str] | None,
    recency: str | None,
    max_results: int,
) -> list[WebSearchResult]:
    """Return no results until a real provider is added in Sprint task 9.3."""
    del query, allowed_domains, recency, max_results
    return []


_search_provider: SearchProvider = _mock_search_provider


def _normalize_allowed_domains(
    allowed_domains: list[str] | None,
) -> list[str] | None:
    """Validate and normalize the optional domain allowlist."""
    if allowed_domains is None:
        return None
    if not isinstance(allowed_domains, list):
        raise TypeError("allowed_domains must be a list of domain names or None.")

    normalized_domains: list[str] = []
    for domain in allowed_domains:
        if not isinstance(domain, str):
            raise TypeError("Each allowed domain must be a string.")
        normalized_domain = domain.strip().lower()
        if not normalized_domain:
            raise ValueError("Allowed domains must not be blank.")
        normalized_domains.append(normalized_domain)
    return normalized_domains


def search_web(
    query: str,
    allowed_domains: list[str] | None = None,
    recency: str | None = None,
    max_results: int = 5,
) -> list[WebSearchResult]:
    """Search through the configured provider and return normalized results.

    The initial provider is an offline mock that returns no results. Every
    attempt logs the normalized query and an ISO-8601 UTC timestamp so future
    provider calls remain auditable.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string.")
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank.")

    normalized_domains = _normalize_allowed_domains(allowed_domains)

    if recency is not None:
        if not isinstance(recency, str):
            raise TypeError("recency must be a string or None.")
        recency = recency.strip()
        if not recency:
            raise ValueError("recency must not be blank.")

    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise TypeError("max_results must be an integer.")
    if max_results < 1:
        raise ValueError("max_results must be a positive integer.")

    searched_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Controlled web search requested: query=%r timestamp=%s",
        normalized_query,
        searched_at,
        extra={
            "web_search_query": normalized_query,
            "web_search_timestamp": searched_at,
        },
    )

    raw_results = _search_provider(
        normalized_query,
        normalized_domains,
        recency,
        max_results,
    )
    return [
        WebSearchResult.model_validate(result)
        for result in raw_results[:max_results]
    ]
