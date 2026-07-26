"""LangGraph nodes for the controlled Sprint 7 multi-agent workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agents.critic import CriticAgent
from agents.finance import FinanceAgent
from agents.research import ResearchAgent
from agents.strategy import StrategyAgent
from agents.writer import WriterAgent
from rag.retriever import EvidenceChunk
from schemas.agent_outputs import AgentRole, SupervisorPlan
from schemas.source import SourceRecord
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
MAX_EVIDENCE_CHUNKS = 20
MAX_EVIDENCE_CHARS_PER_CHUNK = 3_000


def _budget_evidence_chunks(
    evidence_chunks: list[EvidenceChunk],
) -> tuple[list[EvidenceChunk], bool]:
    """Rank and explicitly shorten RAG evidence for the free-tier prompt budget."""
    ranked = sorted(evidence_chunks, key=lambda chunk: chunk.score, reverse=True)
    selected = ranked[:MAX_EVIDENCE_CHUNKS]
    was_limited = len(selected) < len(evidence_chunks)
    budgeted: list[EvidenceChunk] = []
    for chunk in selected:
        if len(chunk.text) <= MAX_EVIDENCE_CHARS_PER_CHUNK:
            budgeted.append(chunk)
            continue
        metadata = dict(chunk.metadata)
        metadata["prompt_budget_truncated"] = True
        metadata["original_text_chars"] = len(chunk.text)
        budgeted.append(
            chunk.model_copy(
                update={
                    "text": (
                        chunk.text[:MAX_EVIDENCE_CHARS_PER_CHUNK].rstrip()
                        + "\n[Evidence shortened for prompt budget.]"
                    ),
                    "metadata": metadata,
                }
            )
        )
        was_limited = True
    return budgeted, was_limited


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


def build_deterministic_supervisor_plan() -> SupervisorPlan:
    """Return the fixed five-role plan without spending an LLM request."""
    task_specs: tuple[
        tuple[AgentRole, str, list[str], list[str], str],
        ...,
    ] = (
        (
            "research",
            "Collect controlled market, customer, and competitor evidence while "
            "separating supported findings from assumptions.",
            ["user_brief"],
            [],
            "A schema-validated ResearchAnalysis packet and traceable Web sources.",
        ),
        (
            "strategy",
            "Develop evidence-aware positioning, business-model, go-to-market, "
            "and moat hypotheses from the validated inputs.",
            ["user_brief", "research_analysis"],
            ["research_task"],
            "A schema-validated StrategyAnalysis packet.",
        ),
        (
            "finance",
            "Build cautious revenue, cost, unit-economics, and break-even "
            "assumptions with explicit validation gaps.",
            ["user_brief", "research_analysis", "strategy_analysis"],
            ["research_task", "strategy_task"],
            "A schema-validated FinanceAssumptions packet.",
        ),
        (
            "writer",
            "Assemble the complete proposal from validated specialist packets "
            "and the dynamically supplied evidence whitelist.",
            [
                "user_brief",
                "research_analysis",
                "strategy_analysis",
                "finance_assumptions",
                "web_sources",
                "evidence_chunks",
            ],
            ["research_task", "strategy_task", "finance_task"],
            "A schema-validated, citation-checked ProposalDraft.",
        ),
        (
            "critic",
            "Review the proposal for logic, financial consistency, evidence "
            "quality, and unresolved citation gaps without rewriting it.",
            ["proposal_draft", "source_metadata"],
            ["writer_task"],
            "A schema-validated CritiqueReport.",
        ),
    )
    return SupervisorPlan.model_validate(
        {
            "plan_summary": (
                "Execute the fixed five specialist roles once in a finite, "
                "auditable dependency order."
            ),
            "tasks": [
                {
                    "task_id": f"{role}_task",
                    "agent_role": role,
                    "objective": objective,
                    "input_requirements": requirements,
                    "expected_output": expected_output,
                    "depends_on": dependencies,
                }
                for (
                    role,
                    objective,
                    requirements,
                    dependencies,
                    expected_output,
                ) in task_specs
            ],
            "selected_agents": list(REQUIRED_AGENT_ROLES),
            "skipped_agents": [],
            "needs_human_review": [],
        }
    )


def supervisor_agent_node(state: WorkflowState) -> WorkflowState:
    """Install the deterministic fixed-role plan for this controlled graph."""
    if not state.get("user_brief"):
        raise ValueError("supervisor_agent_node requires user_brief in state.")
    plan = build_deterministic_supervisor_plan()
    return {
        "supervisor_plan": plan.model_dump(),
        "current_step": "supervisor",
    }


def research_agent_node(
    state: WorkflowState,
    *,
    agent: ResearchAgent,
    source_sink: Callable[[str, list[SourceRecord]], None] | None = None,
) -> WorkflowState:
    """Run controlled web research, persist it, then produce analysis."""
    user_brief = dict(state.get("user_brief") or {})
    user_brief["supervisor_task"] = _supervisor_task(state, "research")
    web_sources = agent.collect_web_sources(user_brief)
    run_id = state.get("run_id")
    if source_sink is not None and run_id:
        source_sink(run_id, web_sources)
    user_brief["web_research_sources"] = [
        source.model_dump(mode="json") for source in web_sources
    ]
    analysis = agent.run(user_brief)
    return {
        "research_analysis": analysis.model_dump(),
        "web_sources": [
            source.model_dump(mode="json") for source in web_sources
        ],
        "web_search_warnings": [
            {
                "agent_name": warning.agent_name,
                "query": warning.query,
                "error_type": warning.error_type,
                "message": warning.message,
            }
            for warning in agent.web_search_warnings
        ],
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
    if any(not isinstance(chunk, EvidenceChunk) for chunk in evidence_chunks):
        raise TypeError("evidence_provider must return EvidenceChunk instances.")
    budgeted_chunks, was_limited = _budget_evidence_chunks(evidence_chunks)
    has_rag = bool(budgeted_chunks)
    has_web = bool(state.get("web_sources"))
    if has_rag and has_web:
        evidence_mode = "rag_and_web"
    elif has_rag:
        evidence_mode = "rag_only"
    elif has_web:
        evidence_mode = "web_only"
    else:
        evidence_mode = "no_external_evidence"
    return {
        "evidence_chunks": [
            chunk.model_dump(mode="json") for chunk in budgeted_chunks
        ],
        "evidence_mode": evidence_mode,
        "low_confidence_required": not has_rag,
        "evidence_was_budget_limited": was_limited,
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
        "web_sources": state.get("web_sources", []),
        "evidence_chunks": state.get("evidence_chunks", []),
        "evidence_mode": state.get("evidence_mode", "no_external_evidence"),
        "low_confidence_required": state.get("low_confidence_required", True),
        "evidence_was_budget_limited": state.get(
            "evidence_was_budget_limited",
            False,
        ),
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
    critique = agent.run(
        {
            "proposal_draft": proposal_draft,
            "sources": state.get("web_sources", []),
        }
    )
    return {
        "critique_report": critique.model_dump(),
        "current_step": "critic",
    }
