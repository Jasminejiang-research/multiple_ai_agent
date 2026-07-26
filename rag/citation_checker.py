"""Deterministic citation checks driven by structured evidence metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.workflow import EvidenceStatus, StructuredClaim

ClaimType = Literal["market_size", "competitor", "trend", "financial_benchmark"]
CitationFailureReason = Literal[
    "missing_claim_source_id",
    "missing_content_citation",
    "missing_key_claim_citation",
    "unknown_source_id",
    "confidence_not_low",
]

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

    claim_index: int = Field(ge=0)
    claim: str = Field(min_length=1)
    claim_types: list[str] = Field(min_length=1)
    evidence_status: EvidenceStatus = "sourced_fact"
    source_ids: list[str] = Field(default_factory=list)
    content_has_source: bool
    key_claim_has_source: bool
    has_source: bool


class EvidenceGap(BaseModel):
    """A non-factual claim that must remain visibly low confidence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    claim_index: int = Field(ge=0)
    claim_text: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    evidence_status: Literal["assumption", "unsupported", "needs_validation"]
    content_anchor: str = ""


class CitationCoverageReport(BaseModel):
    """Auditable citation coverage for all source-sensitive claims in a section."""

    checks: list[ClaimCitationCheck] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    required_claim_count: int = Field(ge=0)
    cited_claim_count: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)


class CitationFailure(BaseModel):
    """One precise citation failure returned with all sibling failures."""

    model_config = ConfigDict(str_strip_whitespace=True)

    section: str = Field(min_length=1)
    claim_index: int = Field(ge=-1)
    claim_text: str
    claim_type: str = Field(min_length=1)
    evidence_status: EvidenceStatus = "sourced_fact"
    content_has_marker: bool
    key_claim_has_marker: bool
    available_source_ids: list[str] = Field(default_factory=list)
    unknown_source_ids: list[str] = Field(default_factory=list)
    reasons: list[CitationFailureReason] = Field(min_length=1)


class CitationValidationError(ValueError):
    """Validation error retaining the complete structured failure list."""

    def __init__(self, output_name: str, failures: Sequence[CitationFailure]) -> None:
        self.output_name = output_name
        self.failures = list(failures)
        details = "; ".join(
            (
                f"{failure.section}[{failure.claim_index}] "
                f"{','.join(failure.reasons)}"
                + (
                    f" unknown={','.join(failure.unknown_source_ids)}"
                    if failure.unknown_source_ids
                    else ""
                )
            )
            for failure in self.failures
        )
        super().__init__(
            f"{output_name} contains sourced_fact claims without exact inline "
            f"[source_id] citations, invalid evidence-gap confidence, or unknown source IDs "
            f"({len(self.failures)} failure(s)): {details}"
        )

    def validation_feedback(self) -> str:
        """Return the complete machine-readable report for one correction call."""
        return json.dumps(
            [failure.model_dump() for failure in self.failures],
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _section_data(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> tuple[str, list[object] | None, list[object], str, str | None]:
    if isinstance(proposal_section, str):
        return proposal_section.strip(), None, [], "", None
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
        raise TypeError(
            "proposal_section key_claims must be a sequence of strings or claim objects."
        )

    raw_source_ids = raw_section.get("source_ids", [])
    if isinstance(raw_source_ids, (str, bytes)) or not isinstance(
        raw_source_ids, Sequence
    ):
        raise TypeError("proposal_section source_ids must be a sequence of strings.")

    title = raw_section.get("title", "")
    if not isinstance(title, str):
        raise TypeError("proposal_section title must be a string.")

    confidence = raw_section.get("confidence")
    if confidence is not None and not isinstance(confidence, str):
        raise TypeError("proposal_section confidence must be a string.")

    return (
        content.strip(),
        list(raw_claims) if raw_claims is not None else None,
        list(raw_source_ids),
        title.strip(),
        confidence.strip() if confidence is not None else None,
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
    return [claim.text for claim in extract_structured_claims(proposal_section)]


def extract_structured_claims(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> list[StructuredClaim]:
    """Return deduplicated structured claims, accepting legacy claim strings."""
    content, raw_claims, _, title, _ = _section_data(proposal_section)
    if raw_claims is None:
        candidates: list[object] = [
            {
                "text": sentence,
                "claim_type": _claim_types(sentence, section_title=title)[0],
                "evidence_status": "sourced_fact",
                "source_ids": _inline_source_ids(sentence),
                "content_anchor": sentence,
            }
            for sentence in _split_sentences(content)
            if _claim_types(sentence, section_title=title)
        ]
    else:
        candidates = raw_claims

    claims: list[StructuredClaim] = []
    seen: set[str] = set()
    for raw_claim in candidates:
        if isinstance(raw_claim, StructuredClaim):
            claim = raw_claim
        elif isinstance(raw_claim, str):
            normalized = raw_claim.strip()
            if not normalized:
                continue
            claim = StructuredClaim(
                text=normalized,
                claim_type="general",
                evidence_status="assumption",
                source_ids=[],
                content_anchor=normalized,
            )
        elif isinstance(raw_claim, BaseModel):
            claim = StructuredClaim.model_validate(raw_claim.model_dump(mode="python"))
        elif isinstance(raw_claim, Mapping):
            claim = StructuredClaim.model_validate(raw_claim)
        else:
            raise TypeError(
                "proposal_section key_claims must contain only strings or claim objects."
            )
        if claim.text not in seen:
            seen.add(claim.text)
            claims.append(claim)
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

    inline_ids = {
        source_id.casefold() for source_id in _inline_source_ids(normalized_claim)
    }
    return any(
        source_id.casefold() in inline_ids
        for source_id in _normalize_source_ids(source_ids)
    )


def _has_all_exact_markers(text: str, source_ids: Iterable[str]) -> bool:
    """Return whether every declared source has an exact bracketed marker."""
    normalized_source_ids = _normalize_source_ids(source_ids)
    if not normalized_source_ids:
        return False
    inline_ids = {source_id.casefold() for source_id in _inline_source_ids(text)}
    return all(source_id.casefold() in inline_ids for source_id in normalized_source_ids)


def _claim_with_inline_context(
    claim: str,
    content: str,
    *,
    content_anchor: str = "",
) -> str:
    """Use the matching content sentence when structured claims omit inline refs."""
    for anchor in (content_anchor, claim):
        normalized_anchor = anchor.strip()
        if not normalized_anchor:
            continue
        for sentence in _split_sentences(content):
            if normalized_anchor in sentence or sentence in normalized_anchor:
                return sentence
    return ""


_INLINE_SOURCE_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_.:/-]*)\]")


def _inline_source_ids(text: str) -> list[str]:
    """Extract bracketed source IDs without treating ordinary prose as a citation."""
    return list(dict.fromkeys(_INLINE_SOURCE_MARKER.findall(text)))


def check_citations(
    proposal_section: str | Mapping[str, object] | BaseModel,
    *,
    allowed_source_ids: Iterable[str] | None = None,
) -> CitationCoverageReport:
    """Check sourced facts and report non-factual claims as evidence gaps."""
    content, _, _, _, _ = _section_data(proposal_section)
    if allowed_source_ids is not None:
        _normalize_source_ids(allowed_source_ids)
    checks: list[ClaimCitationCheck] = []
    evidence_gaps: list[EvidenceGap] = []

    for claim_index, claim in enumerate(extract_structured_claims(proposal_section)):
        if claim.evidence_status != "sourced_fact":
            evidence_gaps.append(
                EvidenceGap(
                    claim_index=claim_index,
                    claim_text=claim.text,
                    claim_type=claim.claim_type,
                    evidence_status=claim.evidence_status,
                    content_anchor=claim.content_anchor,
                )
            )
            continue
        source_ids = _normalize_source_ids(claim.source_ids)
        content_context = _claim_with_inline_context(
            claim.text,
            content,
            content_anchor=claim.content_anchor,
        )
        content_has_source = _has_all_exact_markers(content_context, source_ids)
        key_claim_has_source = _has_all_exact_markers(claim.text, source_ids)
        checks.append(
            ClaimCitationCheck(
                claim_index=claim_index,
                claim=claim.text,
                claim_types=[claim.claim_type],
                source_ids=source_ids,
                content_has_source=content_has_source,
                key_claim_has_source=key_claim_has_source,
                has_source=content_has_source and key_claim_has_source,
            )
        )

    cited_count = sum(check.has_source for check in checks)
    required_count = len(checks)
    return CitationCoverageReport(
        checks=checks,
        evidence_gaps=evidence_gaps,
        required_claim_count=required_count,
        cited_claim_count=cited_count,
        coverage_score=cited_count / required_count if required_count else 1.0,
    )


def citation_coverage_score(
    proposal_section: str | Mapping[str, object] | BaseModel,
) -> float:
    """Return the 0–1 citation coverage score for source-sensitive claims."""
    return check_citations(proposal_section).coverage_score


def validate_proposal_source_allowlist(
    proposal: BaseModel | Mapping[str, object],
    allowed_source_ids: Iterable[str],
    *,
    output_name: str = "ProposalDraft",
) -> None:
    """Reject all source IDs absent from the supplied whitelist in one pass."""
    failures = [
        failure
        for failure in collect_proposal_citation_failures(
            proposal,
            allowed_source_ids=allowed_source_ids,
        )
        if "unknown_source_id" in failure.reasons
    ]
    if failures:
        raise CitationValidationError(output_name, failures)


def collect_proposal_citation_failures(
    proposal: BaseModel | Mapping[str, object],
    *,
    allowed_source_ids: Iterable[str] | None = None,
) -> list[CitationFailure]:
    """Return every missing and unknown citation failure across the proposal."""
    from schemas.workflow import PROPOSAL_SECTION_FIELD_NAMES, ProposalDraft

    validated = (
        proposal
        if isinstance(proposal, ProposalDraft)
        else ProposalDraft.model_validate(proposal)
    )
    if allowed_source_ids is None:
        available_source_ids = _normalize_source_ids(
            source_id
            for field_name in PROPOSAL_SECTION_FIELD_NAMES
            for source_id in getattr(validated, field_name).source_ids
        )
    else:
        available_source_ids = _normalize_source_ids(allowed_source_ids)
    available = set(available_source_ids)

    failures: list[CitationFailure] = []
    for field_name in PROPOSAL_SECTION_FIELD_NAMES:
        section = getattr(validated, field_name)
        claims = extract_structured_claims(section)
        attributed_unknown_ids: set[str] = set()

        for claim_index, claim in enumerate(claims):
            claim_type = claim.claim_type
            context = _claim_with_inline_context(
                claim.text,
                section.content,
                content_anchor=claim.content_anchor,
            )
            content_has_marker = _has_all_exact_markers(
                context,
                claim.source_ids,
            )
            key_claim_has_marker = _has_all_exact_markers(
                claim.text,
                claim.source_ids,
            )
            referenced_ids = _normalize_source_ids(
                [
                    *claim.source_ids,
                    *_inline_source_ids(claim.text),
                    *_inline_source_ids(context),
                ]
            )
            unknown_source_ids = sorted(
                source_id for source_id in referenced_ids if source_id not in available
            )
            attributed_unknown_ids.update(unknown_source_ids)

            reasons: list[CitationFailureReason] = []
            citation_required = claim.evidence_status == "sourced_fact"
            if citation_required and not claim.source_ids:
                reasons.append("missing_claim_source_id")
            if citation_required and not content_has_marker:
                reasons.append("missing_content_citation")
            if citation_required and not key_claim_has_marker:
                reasons.append("missing_key_claim_citation")
            if unknown_source_ids:
                reasons.append("unknown_source_id")
            if (
                claim.evidence_status != "sourced_fact"
                and section.confidence != "low"
            ):
                reasons.append("confidence_not_low")

            if reasons:
                failures.append(
                    CitationFailure(
                        section=field_name,
                        claim_index=claim_index,
                        claim_text=claim.text,
                        claim_type=claim_type,
                        evidence_status=claim.evidence_status,
                        content_has_marker=content_has_marker,
                        key_claim_has_marker=key_claim_has_marker,
                        available_source_ids=available_source_ids,
                        unknown_source_ids=unknown_source_ids,
                        reasons=reasons,
                    )
                )

        orphan_unknown_ids = sorted(
            source_id
            for source_id in section.source_ids
            if source_id not in available and source_id not in attributed_unknown_ids
        )
        if orphan_unknown_ids:
            failures.append(
                CitationFailure(
                    section=field_name,
                    claim_index=-1,
                    claim_text="",
                    claim_type="general",
                    content_has_marker=False,
                    key_claim_has_marker=False,
                    available_source_ids=available_source_ids,
                    unknown_source_ids=orphan_unknown_ids,
                    reasons=["unknown_source_id"],
                )
            )
    return failures


def validate_proposal_citations(
    proposal: BaseModel | Mapping[str, object],
    *,
    output_name: str = "ProposalDraft",
    allowed_source_ids: Iterable[str] | None = None,
) -> list[CitationFailure]:
    """Raise once with all failures, or return an empty failure list."""
    failures = collect_proposal_citation_failures(
        proposal,
        allowed_source_ids=allowed_source_ids,
    )
    if failures:
        raise CitationValidationError(output_name, failures)
    return failures
