"""Controlled LangGraph assembly for the Sprint 7 multi-agent workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from agents.critic import CriticAgent, CriticLLM
from agents.finance import FinanceAgent, FinanceLLM
from agents.research import ResearchAgent, ResearchLLM
from agents.strategy import StrategyAgent, StrategyLLM
from agents.supervisor import SupervisorAgent, SupervisorLLM
from agents.writer import WriterAgent, WriterLLM
from rag.index import VectorIndex
from rag.knowledge_base import (
    DEFAULT_KNOWLEDGE_BASE_DIR,
    retrieve_writer_evidence,
)
from workflow.logging import (
    SessionFactory,
    WorkflowNode,
    with_agent_output_persistence,
    with_workflow_logging,
)
from workflow.multi_agent_nodes import (
    critic_agent_node,
    finance_agent_node,
    EvidenceProvider,
    rag_retrieval_node,
    research_agent_node,
    strategy_agent_node,
    supervisor_agent_node,
    writer_agent_node,
)
from workflow.nodes import RevisionLLM, export_node, input_validator_node, revision_node
from workflow.state import WorkflowState


def _missing_info_route(state: WorkflowState) -> str:
    """Stop incomplete briefs before the Supervisor or any worker is called."""
    return "missing_info" if state.get("missing_info") else "supervisor"


def _logged_agent_node(
    *,
    step_name: str,
    node: WorkflowNode,
    agent_name: str,
    output_type: str,
    output_field: str,
    session_factory: SessionFactory | None,
) -> WorkflowNode:
    """Add node-level logging and agent-output persistence to one agent call."""
    persisted_node = with_agent_output_persistence(
        node,
        agent_name=agent_name,
        output_type=output_type,
        output_field=output_field,
        session_factory=session_factory,
    )
    return with_workflow_logging(step_name, persisted_node, session_factory)


def build_multi_agent_workflow_graph(
    *,
    supervisor_llm: SupervisorLLM | None = None,
    research_llm: ResearchLLM | None = None,
    strategy_llm: StrategyLLM | None = None,
    finance_llm: FinanceLLM | None = None,
    writer_llm: WriterLLM | None = None,
    critic_llm: CriticLLM | None = None,
    revision_llm: RevisionLLM | None = None,
    evidence_provider: EvidenceProvider | None = None,
    rag_index: VectorIndex | None = None,
    knowledge_base_dir: Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    rag_top_k: int = 3,
    rag_min_score: float = 0.2,
    output_dir: Path | None = None,
    logging_session_factory: SessionFactory | None = None,
) -> Any:
    """Build the finite Supervisor-to-revision multi-agent workflow.

    Every agent runs once in a deterministic order. Before writing, the graph
    retrieves section-relevant knowledge-base evidence with source metadata.
    """
    supervisor = SupervisorAgent(llm_client=supervisor_llm)
    research = ResearchAgent(llm_client=research_llm)
    strategy = StrategyAgent(llm_client=strategy_llm)
    finance = FinanceAgent(llm_client=finance_llm)
    writer = WriterAgent(llm_client=writer_llm)
    critic = CriticAgent(llm_client=critic_llm)
    active_evidence_provider = evidence_provider
    if active_evidence_provider is None:
        active_evidence_provider = lambda brief, sections: retrieve_writer_evidence(
            brief,
            sections,
            index=rag_index,
            knowledge_base_dir=knowledge_base_dir,
            top_k=rag_top_k,
            min_score=rag_min_score,
        )

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
        "supervisor",
        _logged_agent_node(
            step_name="supervisor",
            node=lambda state: supervisor_agent_node(state, agent=supervisor),
            agent_name=supervisor.name,
            output_type="SupervisorPlan",
            output_field="supervisor_plan",
            session_factory=logging_session_factory,
        ),
    )
    graph.add_node(
        "research",
        _logged_agent_node(
            step_name="research",
            node=lambda state: research_agent_node(state, agent=research),
            agent_name=research.name,
            output_type="ResearchAnalysis",
            output_field="research_analysis",
            session_factory=logging_session_factory,
        ),
    )
    graph.add_node(
        "strategy",
        _logged_agent_node(
            step_name="strategy",
            node=lambda state: strategy_agent_node(state, agent=strategy),
            agent_name=strategy.name,
            output_type="StrategyAnalysis",
            output_field="strategy_analysis",
            session_factory=logging_session_factory,
        ),
    )
    graph.add_node(
        "finance",
        _logged_agent_node(
            step_name="finance",
            node=lambda state: finance_agent_node(state, agent=finance),
            agent_name=finance.name,
            output_type="FinanceAssumptions",
            output_field="finance_assumptions",
            session_factory=logging_session_factory,
        ),
    )
    graph.add_node(
        "rag_retrieval",
        with_workflow_logging(
            "rag_retrieval",
            lambda state: rag_retrieval_node(
                state,
                evidence_provider=active_evidence_provider,
            ),
            logging_session_factory,
        ),
    )
    graph.add_node(
        "writer",
        _logged_agent_node(
            step_name="writer",
            node=lambda state: writer_agent_node(state, agent=writer),
            agent_name=writer.name,
            output_type="ProposalDraft",
            output_field="proposal_draft",
            session_factory=logging_session_factory,
        ),
    )
    graph.add_node(
        "critic",
        _logged_agent_node(
            step_name="critic",
            node=lambda state: critic_agent_node(state, agent=critic),
            agent_name=critic.name,
            output_type="CritiqueReport",
            output_field="critique_report",
            session_factory=logging_session_factory,
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
        {"missing_info": END, "supervisor": "supervisor"},
    )
    graph.add_edge("supervisor", "research")
    graph.add_edge("research", "strategy")
    graph.add_edge("strategy", "finance")
    graph.add_edge("finance", "rag_retrieval")
    graph.add_edge("rag_retrieval", "writer")
    graph.add_edge("writer", "critic")
    graph.add_edge("critic", "revision")
    graph.add_edge("revision", "export")
    graph.add_edge("export", END)

    return graph.compile()
