"""End-to-end mock tests for the controlled multi-agent workflow."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rag.retriever import EvidenceChunk
from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
    SupervisorPlan,
)
from schemas.source import SourceQuality, WebSearchResult
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    CritiqueReport,
    ProposalDraft,
    RevisedProposal,
)
from storage.db import Base
from storage.repositories import create_run, get_run, update_run_status
from workflow.logging import MULTI_AGENT_PROMPT_VERSION, MULTI_AGENT_VERSION
from workflow.multi_agent_graph import build_multi_agent_workflow_graph


class FakeJsonLLM:
    """Mock LLM adapter that records prompts and returns canned JSON."""

    def __init__(self, response: str) -> None:
        """Store the JSON response returned by this fake."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


def _complete_brief() -> dict[str, str]:
    """Return a brief that passes the deterministic input validator."""
    return {
        "company_or_product_name": "AI Tutor for MBA Students",
        "industry": "EdTech / AI Education",
        "target_customer": "MBA students and business school applicants",
        "problem": "Students lack personalized business case coaching.",
        "solution": "An AI-driven proposal and case coaching platform.",
        "business_model": "Subscription plus institutional licensing",
        "geography": "US / North America",
        "proposal_goal": "investor",
    }


def _supervisor_plan() -> SupervisorPlan:
    """Return the complete fixed-role plan required by the graph."""
    roles = ("research", "strategy", "finance", "writer", "critic")
    tasks = []
    previous_task: str | None = None
    for role in roles:
        task_id = f"{role}_task"
        tasks.append(
            {
                "task_id": task_id,
                "agent_role": role,
                "objective": (
                    f"Produce the schema-validated {role} packet for the controlled "
                    "proposal workflow without exceeding this agent's responsibility."
                ),
                "input_requirements": ["Use only the brief and prior validated packets."],
                "expected_output": f"A complete schema-validated {role} output packet.",
                "depends_on": [previous_task] if previous_task else [],
            }
        )
        previous_task = task_id
    return SupervisorPlan(
        plan_summary="Run every specialist once in a finite, auditable sequence.",
        tasks=tasks,
        selected_agents=list(roles),
        skipped_agents=[],
        needs_human_review=["Confirm assumptions before external use."],
    )


def _analysis_packets() -> tuple[ResearchAnalysis, StrategyAnalysis, FinanceAssumptions]:
    """Return compatible worker outputs for Research, Strategy, and Finance."""
    finding = {
        "topic": "Personalized coaching",
        "finding": "The brief suggests a need for more personalized coaching support.",
        "rationale": "The stated problem is the lack of tailored business case guidance.",
        "confidence": "medium",
    }
    insight = {
        "topic": "Focused coaching",
        "recommendation": "Position the product around personalized proposal feedback.",
        "rationale": "This recommendation directly addresses the coaching gap in the brief.",
        "confidence": "medium",
    }
    assumption = {
        "topic": "Subscription revenue",
        "assumption": "Subscriptions could provide recurring revenue if demand is validated.",
        "rationale": "The supplied business model includes a subscription option.",
        "confidence": "low",
        "needs_validation": ["Pricing tests"],
    }
    research = ResearchAnalysis(
        analysis_summary="Research observations remain hypotheses pending evidence.",
        market_trends=[finding],
        customer_notes=[finding],
        competitor_assumptions=[finding],
        unsupported_claims=[],
        needs_human_review=["Confirm the initial customer segment."],
    )
    strategy = StrategyAnalysis(
        analysis_summary="The strategy focuses on cautious, testable positioning.",
        value_proposition=[insight],
        business_model_logic=[insight],
        gtm_strategy=[insight],
        moat_hypotheses=[insight],
        unsupported_market_data=[],
        needs_human_review=["Confirm the first acquisition channel."],
    )
    finance = FinanceAssumptions(
        analysis_summary="Financial logic is preliminary and requires validation.",
        revenue_assumptions=[assumption],
        cost_assumptions=[assumption],
        unit_economics_assumptions=[assumption],
        break_even_discussion=(
            "Break-even depends on validated pricing, retention, acquisition, and "
            "delivery-cost assumptions."
        ),
        assumption_notice="All financial figures are assumptions, not forecasts.",
        unsupported_financial_claims=[],
        needs_human_review=["Validate pricing and delivery costs."],
    )
    return research, strategy, finance


def _proposal() -> ProposalDraft:
    """Return a valid Writer output containing all 13 fixed sections."""
    data: dict[str, object] = {"title": "AI Tutor Proposal"}
    for title, field_name in zip(
        PROPOSAL_SECTION_TITLES,
        PROPOSAL_SECTION_FIELD_NAMES,
        strict=True,
    ):
        data[field_name] = {
            "title": title,
            "content": (
                f"This {title} section uses only validated analysis packets and "
                "labels uncertain statements as assumptions requiring validation."
            ),
            "key_claims": [f"The {title} reasoning comes from supplied analysis."],
            "source_ids": [],
            "confidence": "medium",
        }
    return ProposalDraft.model_validate(data)


def _critique() -> CritiqueReport:
    """Return one concrete issue for the Critic output."""
    return CritiqueReport(
        overall_score=7.0,
        issues=[
            {
                "section": "Financial Assumptions",
                "severity": "high",
                "issue_type": "financial_inconsistency",
                "description": "The financial assumptions need clearer units and timing.",
                "suggested_fix": "State the currency, period, and validation needed.",
            }
        ],
        must_fix_before_export=["Clarify financial units before external use."],
    )


def _revised_proposal() -> RevisedProposal:
    """Return a valid Revision Node output based on the Writer draft."""
    return RevisedProposal(
        proposal=_proposal(),
        applied_critique_summary=["Clarified that financial units require validation."],
        unresolved_issues=["External evidence remains unavailable in this phase."],
    )


def _evidence_provider(
    user_brief: dict[str, str],
    sections: tuple[str, ...],
) -> list[EvidenceChunk]:
    """Return one traceable chunk without invoking a production vector index."""
    assert user_brief["company_or_product_name"] == "AI Tutor for MBA Students"
    assert "Market Opportunity" in sections
    return [
        EvidenceChunk(
            source_id="tam-framework-001",
            text="TAM, SAM, and SOM should be separated and assumptions disclosed.",
            score=0.9,
            metadata={
                "file_name": "tam_sam_som.md",
                "chunk_id": "tam-framework-chunk",
                "quote": "TAM, SAM, and SOM should be separated and assumptions disclosed.",
                "matched_sections": ["Market Opportunity"],
            },
        )
    ]


def _web_search_provider(
    query: str,
    allowed_domains: list[str] | None,
    recency: str | None,
    max_results: int,
) -> list[WebSearchResult]:
    """Return one distinct source for each approved research query."""
    assert allowed_domains is None
    assert recency == "last_12_months"
    assert max_results == 5
    scope = "competitor" if "competitors alternatives" in query else "market"
    return [
        WebSearchResult(
            title=f"{scope.title()} evidence",
            url=f"https://example.com/{scope}",
            publisher="Example Research",
            published_date="2026-06-01",
            summary=f"Controlled {scope} evidence for the graph test.",
            relevance_score=0.9,
            source_quality=SourceQuality.RESEARCH_ORG,
        )
    ]


def _session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """Create an isolated in-memory session scope for persistence assertions."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    @contextmanager
    def session_scope() -> Iterator[Session]:
        with SessionLocal() as session:
            yield session

    return session_scope


def test_multi_agent_graph_runs_all_agents_and_persists_outputs() -> None:
    """The graph runs once per agent, revises, exports, and stores six outputs."""
    research, strategy, finance = _analysis_packets()
    llms = {
        "supervisor": FakeJsonLLM(_supervisor_plan().model_dump_json()),
        "research": FakeJsonLLM(research.model_dump_json()),
        "strategy": FakeJsonLLM(strategy.model_dump_json()),
        "finance": FakeJsonLLM(finance.model_dump_json()),
        "writer": FakeJsonLLM(_proposal().model_dump_json()),
        "critic": FakeJsonLLM(_critique().model_dump_json()),
        "revision": FakeJsonLLM(_revised_proposal().model_dump_json()),
    }
    session_scope = _session_factory()
    with session_scope() as session:
        create_run(
            session,
            run_id="multi-agent-run",
            workflow_version=MULTI_AGENT_VERSION,
            prompt_version=MULTI_AGENT_PROMPT_VERSION,
            input_brief=_complete_brief(),
        )
        update_run_status(session, "multi-agent-run", "running")
        session.commit()

    with TemporaryDirectory() as temp_dir:
        graph = build_multi_agent_workflow_graph(
            supervisor_llm=llms["supervisor"],
            research_llm=llms["research"],
            web_search_tool=_web_search_provider,
            strategy_llm=llms["strategy"],
            finance_llm=llms["finance"],
            writer_llm=llms["writer"],
            critic_llm=llms["critic"],
            revision_llm=llms["revision"],
            evidence_provider=_evidence_provider,
            output_dir=Path(temp_dir),
            logging_session_factory=session_scope,
        )
        result = graph.invoke(
            {"run_id": "multi-agent-run", "user_brief": _complete_brief()}
        )

        assert result["current_step"] == "export"
        assert Path(result["output_path"]).is_file()
        assert "## Executive Summary" in result["final_markdown"]
        assert result["evidence_chunks"][0]["source_id"] == "tam-framework-001"
        assert len(result["web_sources"]) == 2
        assert {source["agent_name"] for source in result["web_sources"]} == {
            "Market Research Agent",
            "Competitor Agent",
        }
        assert "tam-framework-001" in llms["writer"].prompts[0]
        assert "https://example.com/market" in llms["research"].prompts[0]
        assert "https://example.com/competitor" in llms["research"].prompts[0]

    assert all(len(llm.prompts) == 1 for llm in llms.values())
    with session_scope() as session:
        run = get_run(session, "multi-agent-run")
        assert run is not None
        assert len(run.node_outputs) == 20
        assert len(run.sources) == 2
        assert {source.agent_name for source in run.sources} == {
            "Market Research Agent",
            "Competitor Agent",
        }
        assert [output.output_type for output in run.agent_outputs] == [
            "SupervisorPlan",
            "ResearchAnalysis",
            "StrategyAnalysis",
            "FinanceAssumptions",
            "ProposalDraft",
            "CritiqueReport",
        ]


def test_multi_agent_graph_stops_before_supervisor_for_incomplete_brief() -> None:
    """Missing required input prevents every agent and revision call."""
    supervisor_llm = FakeJsonLLM(_supervisor_plan().model_dump_json())
    brief = _complete_brief()
    del brief["problem"]
    graph = build_multi_agent_workflow_graph(supervisor_llm=supervisor_llm)

    result = graph.invoke({"user_brief": brief})

    assert result["current_step"] == "input_validator"
    assert "Missing required field: problem" in result["missing_info"]
    assert supervisor_llm.prompts == []
