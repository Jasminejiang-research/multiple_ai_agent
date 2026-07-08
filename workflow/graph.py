"""LangGraph assembly for the deterministic proposal workflow.

Sprint 5.8 wires the already-tested workflow nodes into one controlled graph:
validate -> plan -> write sections -> assemble -> critique -> revise -> export.
The graph keeps the missing-info branch deterministic so incomplete input stops
before any LLM-backed node is called.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from schemas.workflow import RevisedProposal
from workflow.nodes import (
    BasicCriticLLM,
    PlannerLLM,
    RevisionLLM,
    SectionWriterLLM,
    basic_critic_node,
    input_validator_node,
    proposal_assembler_node,
    proposal_planner_node,
    render_proposal_preview,
    revision_node,
    section_writer_node,
)
from workflow.state import WorkflowState

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"


def _safe_slug(value: str) -> str:
    """Return a filesystem-safe lowercase slug for exported proposal files."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "proposal"


def _missing_info_route(state: WorkflowState) -> str:
    """Route incomplete briefs to END and complete briefs to the planner."""
    if state.get("missing_info"):
        return "missing_info"
    return "planner"


def exporter_node(
    state: WorkflowState,
    output_dir: Path | None = None,
) -> WorkflowState:
    """Render the revised proposal to Markdown and save it under ``outputs/``.

    Args:
        state: Current workflow state. Expected to contain ``revised_proposal``.
        output_dir: Optional output directory, mainly for tests.

    Returns:
        A partial state update with Markdown text, saved file path, and step name.
    """
    revised_payload = state.get("revised_proposal")
    if revised_payload is None:
        raise ValueError("exporter_node requires revised_proposal in state.")

    revised_proposal = RevisedProposal.model_validate(revised_payload)
    markdown = render_proposal_preview(revised_proposal.proposal)

    target_dir = output_dir or DEFAULT_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = state.get("run_id", "workflow")
    project_slug = _safe_slug(revised_proposal.proposal.title)
    filename = f"{date_prefix}_{project_slug}_{_safe_slug(run_id)}.md"
    output_path = target_dir / filename
    output_path.write_text(markdown, encoding="utf-8")

    return {
        "markdown": markdown,
        "output_path": str(output_path),
        "current_step": "exporter",
    }


def build_proposal_workflow_graph(
    *,
    planner_llm: PlannerLLM | None = None,
    section_writer_llm: SectionWriterLLM | None = None,
    critic_llm: BasicCriticLLM | None = None,
    revision_llm: RevisionLLM | None = None,
    output_dir: Path | None = None,
) -> Any:
    """Build and compile the Phase 2 deterministic proposal workflow graph.

    Args:
        planner_llm: Optional LLM adapter for the planner node.
        section_writer_llm: Optional LLM adapter for the section writer node.
        critic_llm: Optional LLM adapter for the basic critic node.
        revision_llm: Optional LLM adapter for the revision node.
        output_dir: Optional exporter output directory, mainly for tests.

    Returns:
        A compiled LangGraph application ready to invoke with ``WorkflowState``.
    """
    graph = StateGraph(WorkflowState)

    graph.add_node("validator", input_validator_node)
    graph.add_node(
        "planner",
        lambda state: proposal_planner_node(state, llm_client=planner_llm),
    )
    graph.add_node(
        "section_writer",
        lambda state: section_writer_node(state, llm_client=section_writer_llm),
    )
    graph.add_node("assembler", proposal_assembler_node)
    graph.add_node(
        "critic",
        lambda state: basic_critic_node(state, llm_client=critic_llm),
    )
    graph.add_node(
        "revision",
        lambda state: revision_node(state, llm_client=revision_llm),
    )
    graph.add_node("exporter", lambda state: exporter_node(state, output_dir=output_dir))

    graph.set_entry_point("validator")
    graph.add_conditional_edges(
        "validator",
        _missing_info_route,
        {
            "missing_info": END,
            "planner": "planner",
        },
    )
    graph.add_edge("planner", "section_writer")
    graph.add_edge("section_writer", "assembler")
    graph.add_edge("assembler", "critic")
    graph.add_edge("critic", "revision")
    graph.add_edge("revision", "exporter")
    graph.add_edge("exporter", END)

    return graph.compile()
