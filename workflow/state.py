"""Shared state definitions for the LangGraph proposal workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from schemas.proposal_schema import BusinessProposal


class WorkflowState(TypedDict):
    """State object passed between deterministic workflow nodes.

    The current flat MVP workflow uses a small subset of these fields. The
    optional placeholders match the architecture document without implementing
    future sprint behavior yet.
    """

    user_idea: NotRequired[str]
    run_id: NotRequired[str]
    user_brief: NotRequired[dict[str, Any]]
    missing_info: NotRequired[list[str]]
    proposal_outline: NotRequired[dict[str, Any]]
    section_drafts: NotRequired[dict[str, Any]]
    proposal_draft: NotRequired[dict[str, Any]]
    markdown_preview: NotRequired[str]
    proposal: NotRequired[BusinessProposal]
    markdown: NotRequired[str]
    output_path: NotRequired[str]
    proposal_id: NotRequired[int]
    errors: NotRequired[list[str]]
    current_step: NotRequired[str]


ProposalState = WorkflowState
