"""Deterministic citation checks for source-sensitive proposal claims."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ClaimType = Literal["market_size", "competitor", "trend", "financial_benchmark"]

_CLAIM_PATTERNS: dict[ClaimType, tuple[re.Pattern[str], ...]] = {
    "market_size": (
        re.compile(
            r"\b(?:market size|addressable market|tam|sam|som|market value|"
            r"market worth)\b",
            re.IGNORECASE,
        ),
        re.compile(r"(?:市场规模|市场容量|可服务市场|潜在市场)"),
    ),
    "competitor": (
        re.compile(
            r"\b(?:competitor(?:s)?|competition|competitive landscape|rival(?:s)?|"
            r"market leader(?:s)?|alternative(?:s)?|substitute(?:s)?)\b",
            re.IGNORECASE,
        ),
        re.compile(r"(?:竞争对手|竞品|竞争格局|替代方案|替代品)"),
    ),
    "trend": (
        re.compile(
            r"\b(?:trend(?:s)?|cagr|forecast(?:s|ed)?|project(?:s|ed|ion)?|"
            r"grow(?:s|ing|th)?|declin(?:e|es|ed|ing)|adoption|demand\s+"
            r"(?:is\s+)?(?:rising|falling|increasing|decreasing))\b",
            re.IGNORECASE,
        ),
        re.compile(r"(?:趋势|复合增长率|预计|预测|增长|下降|采用率|需求上升|需求下降)"),
    ),
    "financial_benchmark": (
        re.compile(
            r"\b(?:industry benchmark|financial benchmark|gross margin|net margin|"
            r"ebitda|ltv\s*[:/]?\s*cac|customer acquisition cost|churn rate|"
            r"break-even)\b",
            re.IGNORECASE,
        ),
        re.compile(r"(?:行业基准|财务基准|毛利率|净利率|获客成本|流失率|盈亏平衡)"),
    ),
}


class ClaimCitationCheck(BaseModel):
    """Citation status for one claim that requires source evidence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    claim: str = Field(min_length=1)
    claim_types: list[ClaimType] = Field(min_length=1)
    has_source: bool


class CitationCoverageReport(BaseModel):
    """Auditable citation coverage for all source-sensitive claims in a section."""

    checks: list[ClaimCitationCheck] = Field(default_factory=list)
    required_claim_count: int = Field(ge=0)
    cited_claim_count: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)


def _section_data(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> tuple[str, list[object] | None, list[object], str]:
    if isinstance(proposal_section, str):
        return proposal_section.strip(), None, [], ""
    if isinstance(proposal_section, BaseModel):
        raw_section: Mapping[str, object] = proposal_section.model_dump(mode="python")
    elif isinstance(proposal_section, Mapping):
        raw_section = proposal_section
    else:
        raise TypeError("proposal_section must be a string, mapping, or Pydantic model.")

    content = raw_section.get("content", "")
    if not isinstance(content, str):
        raise TypeError("proposal_section content must be a string.")

    raw_claims = raw_section.get("key_claims")
    if raw_claims is not None and (
        isinstance(raw_claims, (str, bytes)) or not isinstance(raw_claims, Sequence)
    ):
        raise TypeError("proposal_section key_claims must be a sequence of strings.")

    raw_source_ids = raw_section.get("source_ids", [])
    if isinstance(raw_source_ids, (str, bytes)) or not isinstance(
        raw_source_ids, Sequence
    ):
        raise TypeError("proposal_section source_ids must be a sequence of strings.")

    title = raw_section.get("title", "")
    if not isinstance(title, str):
        raise TypeError("proposal_section title must be a string.")

    return (
        content.strip(),
        list(raw_claims) if raw_claims is not None else None,
        list(raw_source_ids),
        title.strip(),
    )


def _split_sentences(content: str) -> list[str]:
    """Split English and CJK prose without breaking decimal numbers."""
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+|\n+", content)
        if sentence.strip()
    ]


def _claim_types(claim: str, *, section_title: str = "") -> list[ClaimType]:
    types = [
        claim_type
        for claim_type, patterns in _CLAIM_PATTERNS.items()
        if any(pattern.search(claim) for pattern in patterns)
    ]
    if re.search(r"(?:competitor analysis|competitive landscape|竞品|竞争)", section_title, re.I):
        if "competitor" not in types:
            types.append("competitor")
    return types


def extract_key_claims(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> list[str]:
    """Extract normalized key claims from a proposal section.

    Structured ``key_claims`` are authoritative when present. For plain prose,
    source-sensitive market-size, competitor, trend, and financial-benchmark
    sentences are treated as key claims.
    """
    content, raw_claims, _, title = _section_data(proposal_section)
    if raw_claims is not None:
        candidates = raw_claims
    else:
        candidates = [
            sentence
            for sentence in _split_sentences(content)
            if _claim_types(sentence, section_title=title)
        ]

    claims: list[str] = []
    seen: set[str] = set()
    for claim in candidates:
        if not isinstance(claim, str):
            raise TypeError("proposal_section key_claims must contain only strings.")
        normalized = claim.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            claims.append(normalized)
    return claims


def _normalize_source_ids(source_ids: Iterable[str]) -> list[str]:
    if isinstance(source_ids, (str, bytes)):
        raise TypeError("source_ids must be an iterable of strings, not a string.")

    normalized: list[str] = []
    for source_id in source_ids:
        if not isinstance(source_id, str):
            raise TypeError("source_ids must contain only strings.")
        value = source_id.strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def check_claim_has_source(claim: str, source_ids: Iterable[str]) -> bool:
    """Return whether a claim contains an exact reference to an allowed source ID."""
    if not isinstance(claim, str):
        raise TypeError("claim must be a string.")
    normalized_claim = claim.strip()
    if not normalized_claim:
        return False

    return any(
        re.search(
            rf"(?<![\w-]){re.escape(source_id)}(?![\w-])",
            normalized_claim,
            flags=re.IGNORECASE,
        )
        is not None
        for source_id in _normalize_source_ids(source_ids)
    )


def _claim_with_inline_context(claim: str, content: str) -> str:
    """Use the matching content sentence when structured claims omit inline refs."""
    if not content or claim in content:
        for sentence in _split_sentences(content):
            if claim in sentence:
                return sentence
    return claim


def check_citations(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> CitationCoverageReport:
    """Check required claims and return their citation coverage report."""
    content, _, raw_source_ids, title = _section_data(proposal_section)
    source_ids = _normalize_source_ids(raw_source_ids)
    checks: list[ClaimCitationCheck] = []

    for claim in extract_key_claims(proposal_section):
        claim_types = _claim_types(claim, section_title=title)
        if not claim_types:
            continue
        check_text = _claim_with_inline_context(claim, content)
        checks.append(
            ClaimCitationCheck(
                claim=claim,
                claim_types=claim_types,
                has_source=check_claim_has_source(check_text, source_ids),
            )
        )

    cited_count = sum(check.has_source for check in checks)
    required_count = len(checks)
    return CitationCoverageReport(
        checks=checks,
        required_claim_count=required_count,
        cited_claim_count=cited_count,
        coverage_score=cited_count / required_count if required_count else 1.0,
    )


def citation_coverage_score(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> float:
    """Return the 0–1 citation coverage score for source-sensitive claims."""
    return check_citations(proposal_section).coverage_score
