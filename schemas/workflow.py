"""Pydantic schemas for deterministic proposal workflow node outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROPOSAL_SECTION_TITLES: tuple[str, ...] = (
    "Executive Summary",
    "Problem",
    "Target Customer",
    "Market Opportunity",
    "Solution",
    "Value Proposition",
    "Competitor Analysis",
    "Business Model",
    "Go-to-Market Strategy",
    "Financial Assumptions",
    "Risks and Mitigations",
    "Implementation Roadmap",
    "Appendix",
)
CRITIQUE_MAX_ISSUES = 12
CRITIQUE_MAX_MUST_FIX = 8

PROPOSAL_SECTION_FIELD_NAMES: tuple[str, ...] = (
    "executive_summary",
    "problem",
    "target_customer",
    "market_opportunity",
    "solution",
    "value_proposition",
    "competitor_analysis",
    "business_model",
    "go_to_market_strategy",
    "financial_assumptions",
    "risks_and_mitigations",
    "implementation_roadmap",
    "appendix",
)

SECTION_FIELD_BY_TITLE: dict[str, str] = dict(
    zip(PROPOSAL_SECTION_TITLES, PROPOSAL_SECTION_FIELD_NAMES, strict=True)
)

ClaimType = Literal[
    "market_size",
    "competitor",
    "trend",
    "financial_benchmark",
    "customer",
    "product",
    "operational",
    "regulatory",
    "general",
]
EvidenceStatus = Literal[
    "sourced_fact",
    "assumption",
    "unsupported",
    "needs_validation",
]
ProposalSectionFieldName = Literal[
    "executive_summary",
    "problem",
    "target_customer",
    "market_opportunity",
    "solution",
    "value_proposition",
    "competitor_analysis",
    "business_model",
    "go_to_market_strategy",
    "financial_assumptions",
    "risks_and_mitigations",
    "implementation_roadmap",
    "appendix",
]


class StructuredClaim(BaseModel):
    """One auditable proposal claim and its evidence disposition."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: Annotated[
        str,
        Field(min_length=1, description="The exact claim text shown to reviewers."),
    ]
    claim_type: Annotated[
        ClaimType,
        Field(description="Semantic claim category used by citation policy."),
    ]
    evidence_status: Annotated[
        EvidenceStatus,
        Field(
            description=(
                "Whether the claim is sourced fact, an assumption, unsupported, "
                "or awaiting validation."
            )
        ),
    ]
    source_ids: Annotated[
        list[str],
        Field(
            max_length=8,
            description="Exact source IDs that directly support this claim.",
        ),
    ]
    content_anchor: Annotated[
        str,
        Field(
            min_length=1,
            description=(
                "Exact prose excerpt used to locate the claim in section content."
            ),
        ),
    ]

    @model_validator(mode="after")
    def normalize_evidence_metadata(self) -> "StructuredClaim":
        """Deduplicate IDs and provide a useful anchor for legacy claim strings."""
        self.source_ids = list(dict.fromkeys(self.source_ids))
        return self

    def __str__(self) -> str:
        """Preserve readable formatting in legacy string-oriented renderers."""
        return self.text


def _normalize_structured_claim_inputs(value: object) -> object:
    """Convert legacy ``list[str]`` claim payloads to structured objects."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("key_claims must be a sequence of strings or claim objects.")

    normalized: list[object] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(
                    {
                        "text": text,
                        "claim_type": "general",
                        "evidence_status": "assumption",
                        "source_ids": [],
                        "content_anchor": text,
                    }
                )
        elif isinstance(item, (StructuredClaim, Mapping)):
            normalized.append(item)
        else:
            raise TypeError(
                "key_claims must contain only strings, mappings, or StructuredClaim objects."
            )
    return normalized


class ProposalOutlineSection(BaseModel):
    """Planning notes for one fixed section of the final proposal."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        Literal[
            "Executive Summary",
            "Problem",
            "Target Customer",
            "Market Opportunity",
            "Solution",
            "Value Proposition",
            "Competitor Analysis",
            "Business Model",
            "Go-to-Market Strategy",
            "Financial Assumptions",
            "Risks and Mitigations",
            "Implementation Roadmap",
            "Appendix",
        ],
        Field(description="One of the 13 required proposal section titles."),
    ]
    objective: Annotated[
        str,
        Field(
            min_length=10,
            description="What this section must accomplish for the reader.",
        ),
    ]
    key_points: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=6,
            description="Concise points the section writer should cover.",
        ),
    ]
    evidence_needs: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=5,
            description="Facts or sources needed later; do not invent them here.",
        ),
    ]


class ProposalOutline(BaseModel):
    """Structured output from the ProposalPlanner workflow node."""

    model_config = ConfigDict(str_strip_whitespace=True)

    proposal_title: Annotated[
        str,
        Field(min_length=2, max_length=120, description="Working proposal title."),
    ]
    positioning_summary: Annotated[
        str,
        Field(
            min_length=20,
            description="Short strategic framing based only on the user brief.",
        ),
    ]
    target_reader: Annotated[
        str,
        Field(
            min_length=3,
            description="Primary reader implied by the proposal goal.",
        ),
    ]
    sections: Annotated[
        list[ProposalOutlineSection],
        Field(
            min_length=13,
            max_length=13,
            description="Exactly one outline item for each fixed proposal section.",
        ),
    ]
    key_assumptions: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Explicit assumptions caused by incomplete information.",
        ),
    ]
    needs_human_review: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Planning uncertainties the user should review.",
        ),
    ]

    @model_validator(mode="after")
    def ensure_required_sections_in_order(self) -> "ProposalOutline":
        """Require the outline to cover each fixed proposal section once."""
        titles = tuple(section.title for section in self.sections)
        if titles != PROPOSAL_SECTION_TITLES:
            raise ValueError("ProposalOutline.sections must match the 13 fixed titles in order.")
        return self


class SectionDraft(BaseModel):
    """Draft prose for one fixed proposal section from the SectionWriter node."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        Literal[
            "Executive Summary",
            "Problem",
            "Target Customer",
            "Market Opportunity",
            "Solution",
            "Value Proposition",
            "Competitor Analysis",
            "Business Model",
            "Go-to-Market Strategy",
            "Financial Assumptions",
            "Risks and Mitigations",
            "Implementation Roadmap",
            "Appendix",
        ],
        Field(description="One of the 13 required proposal section titles."),
    ]
    content: Annotated[
        str,
        Field(
            min_length=40,
            description="Draft section prose based only on the brief and outline.",
        ),
    ]
    key_claims: Annotated[
        list[StructuredClaim],
        Field(
            default_factory=list,
            max_length=8,
            description="Structured claims made in the draft for later review.",
        ),
    ]
    source_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Source IDs used by the draft; empty until evidence exists.",
        ),
    ]
    confidence: Annotated[
        Literal["high", "medium", "low"],
        Field(description="Confidence level for this draft section."),
    ] = "medium"

    @field_validator("key_claims", mode="before")
    @classmethod
    def accept_legacy_key_claims(cls, value: object) -> object:
        """Accept legacy strings while always storing structured claims."""
        return _normalize_structured_claim_inputs(value)

    @model_validator(mode="after")
    def align_claim_evidence(self) -> "SectionDraft":
        """Propagate claim sources and downgrade sections with evidence gaps."""
        source_ids = list(self.source_ids)
        for claim in self.key_claims:
            for source_id in claim.source_ids:
                if source_id not in source_ids:
                    source_ids.append(source_id)
        self.source_ids = source_ids
        if any(
            claim.evidence_status != "sourced_fact" for claim in self.key_claims
        ):
            self.confidence = "low"
        return self


class SectionDrafts(BaseModel):
    """Structured output from the SectionWriter workflow node."""

    model_config = ConfigDict(str_strip_whitespace=True)

    proposal_title: Annotated[
        str,
        Field(min_length=2, max_length=120, description="Working proposal title."),
    ]
    sections: Annotated[
        list[SectionDraft],
        Field(
            min_length=13,
            max_length=13,
            description="Exactly one draft for each fixed proposal section.",
        ),
    ]
    writing_notes: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Assumptions or caveats for later assembler/critic nodes.",
        ),
    ]

    @model_validator(mode="after")
    def ensure_required_sections_in_order(self) -> "SectionDrafts":
        """Require the drafts to cover each fixed proposal section once."""
        titles = tuple(section.title for section in self.sections)
        if titles != PROPOSAL_SECTION_TITLES:
            raise ValueError("SectionDrafts.sections must match the 13 fixed titles in order.")
        return self


class ProposalSection(BaseModel):
    """One validated section in the assembled proposal draft.

    The assembler copies each SectionWriter draft into this stricter final
    section shape before downstream critique or export nodes can use it.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        Literal[
            "Executive Summary",
            "Problem",
            "Target Customer",
            "Market Opportunity",
            "Solution",
            "Value Proposition",
            "Competitor Analysis",
            "Business Model",
            "Go-to-Market Strategy",
            "Financial Assumptions",
            "Risks and Mitigations",
            "Implementation Roadmap",
            "Appendix",
        ],
        Field(description="One of the 13 required proposal section titles."),
    ]
    content: Annotated[
        str,
        Field(min_length=40, description="Validated prose for this proposal section."),
    ]
    key_claims: Annotated[
        list[StructuredClaim],
        Field(
            default_factory=list,
            max_length=8,
            description="Structured claims carried forward for critique.",
        ),
    ]
    source_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Source IDs supporting the section, empty until evidence exists.",
        ),
    ]
    confidence: Annotated[
        Literal["high", "medium", "low"],
        Field(description="Confidence level for this assembled section."),
    ] = "medium"

    @field_validator("key_claims", mode="before")
    @classmethod
    def accept_legacy_key_claims(cls, value: object) -> object:
        """Accept legacy strings while always storing structured claims."""
        return _normalize_structured_claim_inputs(value)

    @model_validator(mode="after")
    def align_claim_evidence(self) -> "ProposalSection":
        """Propagate claim sources and downgrade sections with evidence gaps."""
        source_ids = list(self.source_ids)
        for claim in self.key_claims:
            for source_id in claim.source_ids:
                if source_id not in source_ids:
                    source_ids.append(source_id)
        self.source_ids = source_ids
        if any(
            claim.evidence_status != "sourced_fact" for claim in self.key_claims
        ):
            self.confidence = "low"
        return self


class ProposalDraft(BaseModel):
    """Full deterministic proposal assembled from exactly 13 section drafts."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        str,
        Field(min_length=2, max_length=120, description="Working proposal title."),
    ]
    global_source_ids: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Deduplicated source IDs cited across all proposal sections.",
        ),
    ]
    executive_summary: ProposalSection
    problem: ProposalSection
    target_customer: ProposalSection
    market_opportunity: ProposalSection
    solution: ProposalSection
    value_proposition: ProposalSection
    competitor_analysis: ProposalSection
    business_model: ProposalSection
    go_to_market_strategy: ProposalSection
    financial_assumptions: ProposalSection
    risks_and_mitigations: ProposalSection
    implementation_roadmap: ProposalSection
    appendix: ProposalSection

    @model_validator(mode="after")
    def ensure_fixed_sections_match_fields(self) -> "ProposalDraft":
        """Validate section titles and build the proposal-wide source list."""
        global_source_ids: list[str] = []
        for title, field_name in SECTION_FIELD_BY_TITLE.items():
            section = getattr(self, field_name)
            if section.title != title:
                raise ValueError(
                    f"ProposalDraft.{field_name} must have title {title!r}."
                )
            for source_id in section.source_ids:
                if source_id not in global_source_ids:
                    global_source_ids.append(source_id)
        self.global_source_ids = global_source_ids
        return self


class CritiqueIssue(BaseModel):
    """A single issue found by the BasicCritic node in the assembled draft.

    Mirrors ``architecture_design.md`` section 8.4. The critic only reports
    problems; it never rewrites the proposal (that is the RevisionNode's job).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    section: Annotated[
        str,
        Field(
            min_length=2,
            description="Section this issue applies to, or 'General' if cross-cutting.",
        ),
    ]
    severity: Annotated[
        Literal["low", "medium", "high", "critical"],
        Field(description="How badly this issue affects proposal quality."),
    ]
    issue_type: Annotated[
        Literal[
            "missing_evidence",
            "logic_gap",
            "financial_inconsistency",
            "unclear_customer",
            "weak_gtm",
            "unsupported_market_claim",
            "hallucination_risk",
            "writing_quality",
        ],
        Field(description="Category of the problem the critic identified."),
    ]
    description: Annotated[
        str,
        Field(min_length=10, description="Concrete explanation of the problem."),
    ]
    suggested_fix: Annotated[
        str,
        Field(min_length=10, description="Actionable guidance for the revision node."),
    ]


class CritiqueReport(BaseModel):
    """Structured critique output from the BasicCritic workflow node.

    Mirrors ``architecture_design.md`` section 8.4. ``overall_score`` is bounded
    to 0-10 per Sprint 2.3 so downstream logic and evaluation stay comparable.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    overall_score: Annotated[
        float,
        Field(
            ge=0.0,
            le=10.0,
            description="Holistic proposal quality score from 0 (poor) to 10 (excellent).",
        ),
    ]
    issues: Annotated[
        list[CritiqueIssue],
        Field(
            default_factory=list,
            max_length=CRITIQUE_MAX_ISSUES,
            description="Specific issues found; empty means no problems detected.",
        ),
    ]
    must_fix_before_export: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=CRITIQUE_MAX_MUST_FIX,
            description="Blocking issues that must be resolved before export.",
        ),
    ]


class RevisedProposal(BaseModel):
    """Structured output from the RevisionNode after critique-driven edits.

    The revised proposal keeps the same fixed 13-section shape as
    ``ProposalDraft`` and records which critique items were applied so the
    workflow can audit the Generate -> Critique -> Revise loop.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    proposal: ProposalDraft
    applied_critique_summary: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=20,
            description="Brief notes describing critique-driven changes made.",
        ),
    ]
    unresolved_issues: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=20,
            description="Critique items that could not be resolved without new evidence.",
        ),
    ]


class RevisedSectionPatch(BaseModel):
    """Replacement for one failed section of an otherwise valid revision."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    section: ProposalSectionFieldName
    replacement: ProposalSection

    @model_validator(mode="after")
    def ensure_title_matches_field(self) -> "RevisedSectionPatch":
        expected_title = dict(
            zip(
                PROPOSAL_SECTION_FIELD_NAMES,
                PROPOSAL_SECTION_TITLES,
                strict=True,
            )
        )[self.section]
        if self.replacement.title != expected_title:
            raise ValueError(
                f"Patch for {self.section} must retain title {expected_title!r}."
            )
        return self


class RevisedProposalPatch(BaseModel):
    """Second-call payload containing only sections that failed validation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    sections: Annotated[
        list[RevisedSectionPatch],
        Field(min_length=1, max_length=13),
    ]

    @model_validator(mode="after")
    def ensure_unique_sections(self) -> "RevisedProposalPatch":
        section_names = [patch.section for patch in self.sections]
        if len(section_names) != len(set(section_names)):
            raise ValueError("RevisedProposalPatch.sections must be unique.")
        return self
