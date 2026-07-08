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
