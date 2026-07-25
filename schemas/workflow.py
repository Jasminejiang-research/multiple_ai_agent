"""Pydantic schemas for deterministic proposal workflow node outputs."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Important claims made in the draft for later review.",
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
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Important claims carried forward for critique.",
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
            description="Specific issues found; empty means no problems detected.",
        ),
    ]
    must_fix_before_export: Annotated[
        list[str],
        Field(
            default_factory=list,
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
