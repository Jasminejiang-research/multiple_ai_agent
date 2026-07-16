"""LangGraph assembly for the deterministic proposal workflow.

Sprint 5.8 wires the already-tested workflow nodes into one controlled graph:
validate -> plan -> write sections -> assemble -> critique -> revise -> export.
The graph keeps the missing-info branch deterministic so incomplete input stops
before any LLM-backed node is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from workflow.logging import SessionFactory, with_workflow_logging
from workflow.nodes import (
    BasicCriticLLM,
    PlannerLLM,
    RevisionLLM,
    SectionWriterLLM,
    basic_critic_node,
    export_node,
    input_validator_node,
    proposal_assembler_node,
    proposal_planner_node,
    revision_node,
    section_writer_node,
)
from workflow.state import WorkflowState


def _missing_info_route(state: WorkflowState) -> str:
    """Route incomplete briefs to END and complete briefs to the planner."""
    if state.get("missing_info"):
        return "missing_info"
    return "planner"


def build_proposal_workflow_graph(
    *,
    planner_llm: PlannerLLM | None = None,
    section_writer_llm: SectionWriterLLM | None = None,
    critic_llm: BasicCriticLLM | None = None,
    revision_llm: RevisionLLM | None = None,
    output_dir: Path | None = None,
    logging_session_factory: SessionFactory | None = None,
) -> Any:
    """Build and compile the Phase 2 deterministic proposal workflow graph.

    Args:
        planner_llm: Optional LLM adapter for the planner node.
        section_writer_llm: Optional LLM adapter for the section writer node.
        critic_llm: Optional LLM adapter for the basic critic node.
        revision_llm: Optional LLM adapter for the revision node.
        output_dir: Optional exporter output directory, mainly for tests.
        logging_session_factory: Optional SQLAlchemy session context factory
            used to persist workflow run logs.

    Returns:
        A compiled LangGraph application ready to invoke with ``WorkflowState``.
    """
    graph = StateGraph(WorkflowState)

    graph.add_node(
        "validator",
        with_workflow_logging(
            "input_validator",
            input_validator_node,
            logging_session_factory,
        ),
    )
    graph.add_node(
        "planner",
        with_workflow_logging(
            "proposal_planner",
            lambda state: proposal_planner_node(state, llm_client=planner_llm),
            logging_session_factory,
        ),
    )
    graph.add_node(
        "section_writer",
        with_workflow_logging(
            "section_writer",
            lambda state: section_writer_node(state, llm_client=section_writer_llm),
            logging_session_factory,
        ),
    )
    graph.add_node(
        "assembler",
        with_workflow_logging(
            "proposal_assembler",
            proposal_assembler_node,
            logging_session_factory,
        ),
    )
    graph.add_node(
        "critic",
        with_workflow_logging(
            "basic_critic",
            lambda state: basic_critic_node(state, llm_client=critic_llm),
            logging_session_factory,
        ),
    )
    graph.add_node(
        "revision",
        with_workflow_logging(
            "revision",
            lambda state: revision_node(state, llm_client=revision_llm),
            logging_session_factory,
        ),
    )
    graph.add_node(
        "export",
        with_workflow_logging(
            "export",
            lambda state: export_node(state, output_dir=output_dir),
            logging_session_factory,
        ),
    )

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
    graph.add_edge("revision", "export")
    graph.add_edge("export", END)

    return graph.compile()
