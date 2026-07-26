"""Shared state definitions for the LangGraph proposal workflow."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

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
    supervisor_plan: NotRequired[dict[str, Any]]
    research_analysis: NotRequired[dict[str, Any]]
    web_sources: NotRequired[list[dict[str, Any]]]
    web_search_warnings: NotRequired[list[str]]
    strategy_analysis: NotRequired[dict[str, Any]]
    finance_assumptions: NotRequired[dict[str, Any]]
    evidence_chunks: NotRequired[list[dict[str, Any]]]
    evidence_mode: NotRequired[str]
    low_confidence_required: NotRequired[bool]
    evidence_was_budget_limited: NotRequired[bool]
    proposal_outline: NotRequired[dict[str, Any]]
    section_drafts: NotRequired[dict[str, Any]]
    proposal_draft: NotRequired[dict[str, Any]]
    markdown_preview: NotRequired[str]
    critique_report: NotRequired[dict[str, Any]]
    revision_checkpoint: NotRequired[dict[str, Any]]
    revised_proposal: NotRequired[dict[str, Any]]
    citation_failures: NotRequired[list[dict[str, Any]]]
    needs_citation_review: NotRequired[bool]
    preflight_warnings: NotRequired[list[str]]
    run_budget: NotRequired[dict[str, Any]]
    proposal: NotRequired[BusinessProposal]
    final_markdown: NotRequired[str]
    markdown: NotRequired[str]
    output_path: NotRequired[str]
    proposal_id: NotRequired[int]
    errors: NotRequired[list[str]]
    current_step: NotRequired[str]


ProposalState = WorkflowState
