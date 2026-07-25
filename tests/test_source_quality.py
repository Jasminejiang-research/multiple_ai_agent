"""Tests for deterministic web source-quality classification."""

from __future__ import annotations

import pytest

from schemas import SourceQuality
from tools.source_quality import classify_source_quality


@pytest.mark.parametrize(
    ("url", "publisher", "expected"),
    [
        (
            "https://openai.com/research/",
            "OpenAI",
            SourceQuality.OFFICIAL,
        ),
        (
            "https://www.sec.gov/Archives/edgar/data/0000320193/"
            "aapl-20250927.htm",
            "U.S. Securities and Exchange Commission",
            SourceQuality.FINANCIAL_REPORT,
        ),
        (
            "https://news.mit.edu/2026/research-example",
            "Massachusetts Institute of Technology",
            SourceQuality.RESEARCH_ORG,
        ),
        (
            "https://www.reuters.com/technology/example/",
            "Reuters",
            SourceQuality.NEWS,
        ),
        (
            "https://example.medium.com/industry-analysis",
            "Example Industry Blog",
            SourceQuality.BLOG,
        ),
    ],
)
def test_classify_source_quality_covers_five_source_types(
    url: str,
    publisher: str,
    expected: SourceQuality,
) -> None:
    """Architecture source classes should be recognized deterministically."""
    assert classify_source_quality(url, publisher) is expected


def test_classify_source_quality_returns_unknown_without_a_known_signal() -> None:
    """Unrecognized sources remain unknown instead of being over-classified."""
    assert (
        classify_source_quality("https://example.net/article", None)
        is SourceQuality.UNKNOWN
    )


def test_financial_report_takes_precedence_over_official_domain() -> None:
    """An SEC-hosted filing is a financial report, not merely official."""
    assert (
        classify_source_quality(
            "https://sec.gov/files/company-10-k.pdf",
            "U.S. Government",
        )
        is SourceQuality.FINANCIAL_REPORT
    )
