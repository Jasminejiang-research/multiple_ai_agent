"""Critic Agent for structured review of proposal drafts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from agents.base import AgentLogHook, BaseAgent
from rag.citation_checker import check_citations, check_claim_has_source
from schemas.source import SourceQuality
from schemas.workflow import (
    CRITIQUE_MAX_ISSUES,
    CRITIQUE_MAX_MUST_FIX,
    PROPOSAL_SECTION_FIELD_NAMES,
    CritiqueIssue,
    CritiqueReport,
    ProposalDraft,
    ProposalSection,
)
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
CRITIC_PROMPT_PATH = ROOT_DIR / "prompts" / "critic_agent.md"
_ENFORCED_CLAIM_TYPES = frozenset(
    {"market_size", "competitor", "trend", "financial_benchmark"}
)
_LOW_SOURCE_QUALITIES = frozenset({SourceQuality.BLOG, SourceQuality.UNKNOWN})
_SEVERITY_PRIORITY = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class CriticLLM(Protocol):
    """Minimal LLM interface used by ``CriticAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


def create_default_critic_llm() -> CriticLLM:
    """Create the default production LLM adapter for the Critic Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), CritiqueReport, temperature=0.2
    )


def load_critic_prompt() -> str:
    """Load the Critic Agent prompt template from disk."""
    if not CRITIC_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Critic Agent prompt not found: {CRITIC_PROMPT_PATH}")
    return CRITIC_PROMPT_PATH.read_text(encoding="utf-8")


def _parse_critic_input(
    input_data: dict[str, Any] | ProposalDraft,
) -> tuple[ProposalDraft, list[Mapping[str, Any]]]:
    """Validate a proposal and optional source metadata supplied for review."""
    raw_proposal: Any = input_data
    raw_sources: Any = []
    if isinstance(input_data, dict) and "proposal_draft" in input_data:
        raw_proposal = input_data["proposal_draft"]
        raw_sources = input_data.get("sources", input_data.get("web_sources", []))

    try:
        proposal_draft = (
            raw_proposal
            if isinstance(raw_proposal, ProposalDraft)
            else ProposalDraft.model_validate(raw_proposal)
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid ProposalDraft: {exc}") from exc

    if isinstance(raw_sources, (str, bytes)) or not isinstance(
        raw_sources, Sequence
    ):
        raise TypeError("Critic source metadata must be a sequence.")

    sources: list[Mapping[str, Any]] = []
    for source in raw_sources:
        if isinstance(source, BaseModel):
            sources.append(source.model_dump(mode="json"))
        elif isinstance(source, Mapping):
            sources.append(source)
        else:
            raise TypeError(
                "Each Critic source record must be a mapping or Pydantic model."
            )
    return proposal_draft, sources


def build_critic_prompt(input_data: dict[str, Any] | ProposalDraft) -> str:
    """Build a Critic prompt from a draft and optional source metadata."""
    proposal_draft, sources = _parse_critic_input(input_data)
    prompt = (
        f"{load_critic_prompt()}\n\n"
        "# ProposalDraft Input JSON\n\n"
        f"```json\n{proposal_draft.model_dump_json(indent=2)}\n```"
    )
    if sources:
        prompt += (
            "\n\n# Source Metadata JSON\n\n"
            f"```json\n{json.dumps(sources, ensure_ascii=False, indent=2, default=str)}\n```"
        )
    return prompt


def parse_critique_report(raw_output: str) -> CritiqueReport:
    """Parse and strictly validate raw Critic JSON as ``CritiqueReport``."""
    try:
        return CritiqueReport.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid CritiqueReport output: {exc}") from exc


def _source_quality_by_id(
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, SourceQuality]:
    """Return normalized quality metadata for source IDs known to the Critic."""
    qualities: dict[str, SourceQuality] = {}
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("Critic source metadata requires a non-blank source_id.")
        raw_quality = source.get("source_quality", SourceQuality.UNKNOWN)
        try:
            qualities[source_id.strip()] = SourceQuality(raw_quality)
        except ValueError as exc:
            raise ValueError(
                f"Invalid source_quality for source {source_id!r}: {raw_quality!r}."
            ) from exc
    return qualities


def _claim_context(section: ProposalSection, claim: str) -> str:
    """Recover the prose sentence when a structured claim omits its marker."""
    if claim not in section.content:
        return claim
    for sentence in re.split(
        r"(?<=[。！？!?])\s*|(?<=\.)\s+|\n+",
        section.content,
    ):
        if claim in sentence:
            return sentence.strip()
    return claim


def _claim_source_ids(section: ProposalSection, claim: str) -> list[str]:
    context = _claim_context(section, claim)
    return [
        source_id
        for source_id in section.source_ids
        if check_claim_has_source(context, [source_id])
    ]


def _budget_critique(
    report: CritiqueReport,
    issues: list[CritiqueIssue],
    must_fix: list[str],
) -> CritiqueReport:
    """Keep revision input bounded while explicitly aggregating overflow."""
    unique_issues: list[CritiqueIssue] = []
    issue_keys: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.section, issue.issue_type, issue.description)
        if key not in issue_keys:
            issue_keys.add(key)
            unique_issues.append(issue)

    if len(unique_issues) > CRITIQUE_MAX_ISSUES:
        ranked = sorted(
            enumerate(unique_issues),
            key=lambda item: (
                -_SEVERITY_PRIORITY[item[1].severity],
                item[0],
            ),
        )
        kept = [
            issue
            for _, issue in ranked[: CRITIQUE_MAX_ISSUES - 1]
        ]
        omitted = len(unique_issues) - len(kept)
        affected_sections = sorted(
            {issue.section for _, issue in ranked[CRITIQUE_MAX_ISSUES - 1 :]}
        )
        kept.append(
            CritiqueIssue(
                section="General",
                severity="high",
                issue_type="logic_gap",
                description=(
                    f"{omitted} additional critique issues were aggregated to "
                    "stay within the free-tier revision budget; affected sections: "
                    + ", ".join(affected_sections)
                    + "."
                ),
                suggested_fix=(
                    "Review the affected sections together and resolve repeated "
                    "evidence, consistency, and clarity gaps as grouped concerns."
                ),
            )
        )
        unique_issues = kept

    unique_must_fix = list(dict.fromkeys(must_fix))
    if len(unique_must_fix) > CRITIQUE_MAX_MUST_FIX:
        kept_must_fix = unique_must_fix[: CRITIQUE_MAX_MUST_FIX - 1]
        omitted = len(unique_must_fix) - len(kept_must_fix)
        kept_must_fix.append(
            f"Resolve {omitted} additional related blocking issues aggregated "
            "for the free-tier revision budget."
        )
        unique_must_fix = kept_must_fix

    return CritiqueReport.model_validate(
        {
            "overall_score": report.overall_score,
            "issues": [issue.model_dump() for issue in unique_issues],
            "must_fix_before_export": unique_must_fix,
        }
    )


def enforce_citation_requirements(
    proposal_draft: ProposalDraft,
    critique_report: CritiqueReport,
    sources: Sequence[Mapping[str, Any]] = (),
) -> CritiqueReport:
    """Deterministically enforce Sprint 9.7 citation severity rules.

    Market-size, competitor, and trend claims without an exact inline source
    marker are always high severity. Claims citing a known blog or
    unclassified source receive a medium-severity source-quality issue.
    """
    proposal = ProposalDraft.model_validate(proposal_draft)
    report = CritiqueReport.model_validate(critique_report)
    source_qualities = _source_quality_by_id(sources)
    issues = list(report.issues)
    must_fix = list(report.must_fix_before_export)

    for field_name in PROPOSAL_SECTION_FIELD_NAMES:
        section = getattr(proposal, field_name)
        citation_report = check_citations(section)
        for check in citation_report.checks:
            enforced_types = sorted(
                set(check.claim_types).intersection(_ENFORCED_CLAIM_TYPES)
            )
            if not enforced_types:
                continue
            claim_kinds = ", ".join(enforced_types)
            if not check.has_source:
                description = (
                    f"Citation enforcement: {claim_kinds} claim lacks an exact "
                    f"inline citation to a source_id: {check.claim}"
                )
                issues.append(
                    CritiqueIssue(
                        section=section.title,
                        severity="high",
                        issue_type=(
                            "unsupported_market_claim"
                            if "market_size" in enforced_types
                            else "missing_evidence"
                        ),
                        description=description,
                        suggested_fix=(
                            "Add a directly supporting source_id marker to the claim "
                            "and section, or remove/caveat the unsupported claim."
                        ),
                    )
                )
                if description not in must_fix:
                    must_fix.append(description)
                continue

            low_quality_ids = sorted(
                source_id
                for source_id in _claim_source_ids(section, check.claim)
                if source_qualities.get(source_id) in _LOW_SOURCE_QUALITIES
            )
            if low_quality_ids:
                issues.append(
                    CritiqueIssue(
                        section=section.title,
                        severity="medium",
                        issue_type="missing_evidence",
                        description=(
                            f"Citation enforcement: {claim_kinds} claim relies on "
                            "low-quality source(s) "
                            f"{', '.join(low_quality_ids)}: {check.claim}"
                        ),
                        suggested_fix=(
                            "Replace or corroborate the citation with an official, "
                            "financial-report, research-organization, or reputable "
                            "news source."
                        ),
                    )
                )

    return _budget_critique(report, issues, must_fix)


class CriticAgent(BaseAgent):
    """Agent that identifies proposal issues without rewriting the draft."""

    def __init__(
        self,
        *,
        llm_client: CriticLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = CRITIC_PROMPT_PATH,
    ) -> None:
        """Create a Critic Agent with an optional injected LLM client."""
        super().__init__(
            name="Critic Agent",
            description=(
                "Reviews unsupported claims, financial consistency, and GTM quality."
            ),
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> CritiqueReport:
        """Return a validated critique and leave the proposal unchanged."""
        if not isinstance(input_data, (dict, ProposalDraft)):
            raise TypeError("CriticAgent input_data must be a dictionary or ProposalDraft.")

        proposal_draft, sources = _parse_critic_input(input_data)
        prompt = build_critic_prompt(input_data)
        llm_client = self._llm_client or create_default_critic_llm()
        raw_output = llm_client.generate_json(prompt)
        critique = parse_critique_report(raw_output)
        return enforce_citation_requirements(proposal_draft, critique, sources)
