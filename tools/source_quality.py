"""Deterministic source-quality classification for web research results."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from schemas import SourceQuality

_FINANCIAL_DOMAINS = frozenset(
    {
        "sec.gov",
    }
)
_FINANCIAL_TERMS = (
    "annual report",
    "financial report",
    "financial statements",
    "investor relations",
    "quarterly results",
    "earnings release",
)
_FINANCIAL_PATH_PATTERN = re.compile(
    r"(?:^|[/_.-])(?:10-k|10-q|8-k|20-f|6-k|annual-report|"
    r"financial-report|financial-statements|investor-relations|"
    r"sec-filings?|earnings)(?:$|[/_.-])"
)

_RESEARCH_DOMAINS = frozenset(
    {
        "arxiv.org",
        "brookings.edu",
        "cern.ch",
        "imf.org",
        "nber.org",
        "nih.gov",
        "oecd.org",
        "pewresearch.org",
        "rand.org",
        "ssrn.com",
        "worldbank.org",
    }
)
_RESEARCH_TERMS = (
    "university",
    "college",
    "academy",
    "research institute",
    "research institution",
    "research center",
    "research centre",
    "laboratory",
)

_NEWS_DOMAINS = frozenset(
    {
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "bloomberg.com",
        "cnbc.com",
        "cnn.com",
        "economist.com",
        "ft.com",
        "nbcnews.com",
        "nytimes.com",
        "reuters.com",
        "theguardian.com",
        "wsj.com",
    }
)
_NEWS_PUBLISHERS = (
    "associated press",
    "bbc",
    "bloomberg",
    "cnbc",
    "cnn",
    "financial times",
    "nbc news",
    "new york times",
    "reuters",
    "the economist",
    "the guardian",
    "wall street journal",
)

_OFFICIAL_DOMAINS = frozenset(
    {
        "europa.eu",
        "un.org",
        "who.int",
    }
)
_GOVERNMENT_DOMAIN_PATTERN = re.compile(
    r"(?:^|\.)(?:gov|govt|gouv|go|gc)(?:\.[a-z]{2})?$"
)
_OFFICIAL_PUBLISHER_TERMS = (
    "government",
    "ministry",
    "department of",
    "commission",
)

_BLOG_DOMAINS = frozenset(
    {
        "blogger.com",
        "ghost.io",
        "medium.com",
        "substack.com",
        "tumblr.com",
        "wordpress.com",
    }
)
_BLOG_TERMS = ("blog", "newsletter", "substack")
_PUBLISHER_SUFFIXES = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "group",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "ltd",
        "plc",
    }
)


def _hostname_and_path(url: str) -> tuple[str, str]:
    """Return normalized URL components, accepting URLs without a scheme."""
    candidate = url.strip()
    if not candidate:
        return "", ""
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = unquote(parsed.path).lower()
    return hostname, path


def _domain_matches(hostname: str, domains: frozenset[str]) -> bool:
    """Return whether a hostname is a listed domain or one of its subdomains."""
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in domains
    )


def _publisher_matches_hostname(hostname: str, publisher: str) -> bool:
    """Detect a company-owned domain from matching publisher and domain names."""
    if not hostname or not publisher:
        return False

    domain_label = hostname.split(".")[-2] if "." in hostname else hostname
    normalized_domain = re.sub(r"[^a-z0-9]", "", domain_label)
    publisher_words = [
        word
        for word in re.findall(r"[a-z0-9]+", publisher)
        if word not in _PUBLISHER_SUFFIXES
    ]
    normalized_publisher = "".join(publisher_words)
    return (
        len(normalized_domain) >= 3
        and (
            normalized_publisher == normalized_domain
            or normalized_publisher.startswith(normalized_domain)
            or normalized_domain.startswith(normalized_publisher)
        )
    )


def classify_source_quality(
    url: str,
    publisher: str | None = None,
) -> SourceQuality:
    """Classify a web source using conservative, explainable heuristics.

    Financial filings take precedence over their official host classification.
    Academic sources use ``research_org`` because that is the category exposed
    by ``WebSearchResult``.
    """
    if not isinstance(url, str):
        raise TypeError("url must be a string.")
    if publisher is not None and not isinstance(publisher, str):
        raise TypeError("publisher must be a string or None.")

    hostname, path = _hostname_and_path(url)
    normalized_publisher = (publisher or "").strip().lower()
    searchable_url = f"{hostname}{path}"

    if (
        _domain_matches(hostname, _FINANCIAL_DOMAINS)
        or _FINANCIAL_PATH_PATTERN.search(searchable_url)
        or any(term in normalized_publisher for term in _FINANCIAL_TERMS)
    ):
        return SourceQuality.FINANCIAL_REPORT

    if (
        hostname.endswith(".edu")
        or ".ac." in hostname
        or hostname.startswith("research.")
        or _domain_matches(hostname, _RESEARCH_DOMAINS)
        or any(term in normalized_publisher for term in _RESEARCH_TERMS)
    ):
        return SourceQuality.RESEARCH_ORG

    if _domain_matches(hostname, _NEWS_DOMAINS) or any(
        publisher_name in normalized_publisher
        for publisher_name in _NEWS_PUBLISHERS
    ):
        return SourceQuality.NEWS

    if (
        _domain_matches(hostname, _OFFICIAL_DOMAINS)
        or _GOVERNMENT_DOMAIN_PATTERN.search(hostname)
        or any(
            term in normalized_publisher
            for term in _OFFICIAL_PUBLISHER_TERMS
        )
        or _publisher_matches_hostname(hostname, normalized_publisher)
    ):
        return SourceQuality.OFFICIAL

    if (
        _domain_matches(hostname, _BLOG_DOMAINS)
        or hostname.startswith("blog.")
        or "/blog/" in f"{path}/"
        or any(term in normalized_publisher for term in _BLOG_TERMS)
    ):
        return SourceQuality.BLOG

    return SourceQuality.UNKNOWN
