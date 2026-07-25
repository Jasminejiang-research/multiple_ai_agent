"""LangGraph nodes for the controlled Sprint 7 multi-agent workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agents.critic import CriticAgent
from agents.finance import FinanceAgent
from agents.research import ResearchAgent
from agents.strategy import StrategyAgent
from agents.supervisor import SupervisorAgent
from agents.writer import WriterAgent
from rag.retriever import EvidenceChunk
from schemas.agent_outputs import AgentRole, SupervisorPlan
from schemas.workflow import PROPOSAL_SECTION_TITLES
from workflow.nodes import render_proposal_preview
from workflow.state import WorkflowState

EvidenceProvider = Callable[
    [Mapping[str, Any], Sequence[str]],
    list[EvidenceChunk],
]

REQUIRED_AGENT_ROLES: tuple[AgentRole, ...] = (
    "research",
    "strategy",
    "finance",
    "writer",
    "critic",
)


def _supervisor_task(state: WorkflowState, role: AgentRole) -> dict[str, Any]:
    """Return the Supervisor task assigned to one required agent role."""
    raw_plan = state.get("supervisor_plan")
    if raw_plan is None:
        raise ValueError(f"{role}_agent_node requires supervisor_plan in state.")

    plan = SupervisorPlan.model_validate(raw_plan)
    for task in plan.tasks:
        if task.agent_role == role:
            return task.model_dump()
    raise ValueError(f"SupervisorPlan does not contain a task for the {role} agent.")


def supervisor_agent_node(
    state: WorkflowState,
    *,
    agent: SupervisorAgent,
) -> WorkflowState:
    """Create and validate the fixed set of tasks used by this controlled graph."""
    plan = agent.run(state.get("user_brief") or {})
    missing_roles = [
        role for role in REQUIRED_AGENT_ROLES if role not in plan.selected_agents
    ]
    if missing_roles:
        raise ValueError(
            "The controlled multi-agent workflow requires Supervisor tasks for: "
            + ", ".join(missing_roles)
        )
    return {
        "supervisor_plan": plan.model_dump(),
        "current_step": "supervisor",
    }


def research_agent_node(
    state: WorkflowState,
    *,
    agent: ResearchAgent,
) -> WorkflowState:
    """Run brief-grounded research under the Supervisor's assigned task."""
    user_brief = dict(state.get("user_brief") or {})
    user_brief["supervisor_task"] = _supervisor_task(state, "research")
    analysis = agent.run(user_brief)
    return {
        "research_analysis": analysis.model_dump(),
        "current_step": "research",
    }


def strategy_agent_node(
    state: WorkflowState,
    *,
    agent: StrategyAgent,
) -> WorkflowState:
    """Run strategy analysis using the brief and Research Agent packet."""
    research_analysis = state.get("research_analysis")
    if research_analysis is None:
        raise ValueError("strategy_agent_node requires research_analysis in state.")
    analysis = agent.run(
        {
            "user_brief": state.get("user_brief") or {},
            "research_analysis": research_analysis,
            "supervisor_task": _supervisor_task(state, "strategy"),
        }
    )
    return {
        "strategy_analysis": analysis.model_dump(),
        "current_step": "strategy",
    }


def finance_agent_node(
    state: WorkflowState,
    *,
    agent: FinanceAgent,
) -> WorkflowState:
    """Run finance analysis using prior research and strategy packets."""
    research_analysis = state.get("research_analysis")
    strategy_analysis = state.get("strategy_analysis")
    if research_analysis is None or strategy_analysis is None:
        raise ValueError(
            "finance_agent_node requires research_analysis and strategy_analysis."
        )
    assumptions = agent.run(
        {
            "user_brief": state.get("user_brief") or {},
            "research_analysis": research_analysis,
            "strategy_analysis": strategy_analysis,
            "supervisor_task": _supervisor_task(state, "finance"),
        }
    )
    return {
        "finance_assumptions": assumptions.model_dump(),
        "current_step": "finance",
    }


def rag_retrieval_node(
    state: WorkflowState,
    *,
    evidence_provider: EvidenceProvider,
) -> WorkflowState:
    """Retrieve source-traceable knowledge before the Writer is called."""
    user_brief = state.get("user_brief") or {}
    evidence_chunks = evidence_provider(user_brief, PROPOSAL_SECTION_TITLES)
    if not evidence_chunks:
        raise ValueError("rag_retrieval_node requires at least one evidence chunk.")
    if any(not isinstance(chunk, EvidenceChunk) for chunk in evidence_chunks):
        raise TypeError("evidence_provider must return EvidenceChunk instances.")
    return {
        "evidence_chunks": [
            chunk.model_dump(mode="json") for chunk in evidence_chunks
        ],
        "current_step": "rag_retrieval",
    }


def writer_agent_node(
    state: WorkflowState,
    *,
    agent: WriterAgent,
) -> WorkflowState:
    """Assemble worker packets and retrieved evidence into a proposal draft."""
    writer_input = {
        "research_analysis": state.get("research_analysis"),
        "strategy_analysis": state.get("strategy_analysis"),
        "finance_assumptions": state.get("finance_assumptions"),
        "evidence_chunks": state.get("evidence_chunks"),
    }
    proposal = agent.run(writer_input)
    return {
        "proposal_draft": proposal.model_dump(),
        "markdown_preview": render_proposal_preview(proposal),
        "current_step": "writer",
    }


def critic_agent_node(
    state: WorkflowState,
    *,
    agent: CriticAgent,
) -> WorkflowState:
    """Review the Writer draft and return issues without rewriting it."""
    proposal_draft = state.get("proposal_draft")
    if proposal_draft is None:
        raise ValueError("critic_agent_node requires proposal_draft in state.")
    critique = agent.run(proposal_draft)
    return {
        "critique_report": critique.model_dump(),
        "current_step": "critic",
    }
