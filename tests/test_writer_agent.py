"""Unit tests for the Writer Agent (Sprint 7.6)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agents.base import AgentLogEvent
from agents.writer import WriterAgent, build_writer_prompt
from rag.retriever import EvidenceChunk
from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
    WriterInput,
)
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
)


def _writer_input() -> WriterInput:
    """Return valid research, strategy, and finance packets for the Writer."""
    finding = {
        "topic": "Personalized coaching need",
        "finding": "The brief suggests students need more personalized coaching support.",
        "rationale": "The stated problem is a lack of tailored business case guidance.",
        "confidence": "medium",
    }
    insight = {
        "topic": "Focused coaching workflow",
        "recommendation": "Position the product around personalized proposal feedback.",
        "rationale": "This directly addresses the coaching gap described in the research packet.",
        "confidence": "medium",
    }
    finance_assumption = {
        "topic": "Subscription revenue",
        "assumption": "Subscriptions could provide recurring revenue if willingness to pay is validated.",
        "rationale": "The supplied strategy identifies subscription as one possible model.",
        "confidence": "low",
        "needs_validation": ["Pricing tests"],
    }

    return WriterInput(
        research_analysis=ResearchAnalysis(
            analysis_summary="Research findings remain hypotheses until evidence is collected.",
            market_trends=[finding],
            customer_notes=[finding],
            competitor_assumptions=[finding],
            unsupported_claims=[
                {
                    "claim": "AI coaching demand is growing rapidly.",
                    "why_unsupported": "No adoption data or external source was supplied.",
                    "needed_evidence": ["Recent adoption research"],
                }
            ],
            needs_human_review=["Confirm the first customer segment."],
        ),
        strategy_analysis=StrategyAnalysis(
            analysis_summary="The strategy emphasizes focused coaching and cautious validation.",
            value_proposition=[insight],
            business_model_logic=[insight],
            gtm_strategy=[{**insight, "confidence": "low"}],
            moat_hypotheses=[{**insight, "confidence": "low"}],
            unsupported_market_data=[],
            needs_human_review=["Confirm the initial acquisition channel."],
        ),
        finance_assumptions=FinanceAssumptions(
            analysis_summary="Financial logic is preliminary and requires validation.",
            revenue_assumptions=[finance_assumption],
            cost_assumptions=[finance_assumption],
            unit_economics_assumptions=[finance_assumption],
            break_even_discussion=(
                "Break-even would depend on validated pricing, retention, acquisition, "
                "and product delivery costs."
            ),
            assumption_notice="All financial figures are assumptions, not forecasts.",
            unsupported_financial_claims=[],
            needs_human_review=["Validate pricing and delivery costs."],
        ),
        web_sources=[
            {
                "source_id": "web-market-research",
                "agent_name": "Market Research Agent",
                "query": "AI education market research",
                "retrieved_at": datetime(2026, 7, 25, tzinfo=timezone.utc),
                "title": "AI Education Market Report",
                "url": "https://example.com/ai-education-market",
                "publisher": "Example Research",
                "published_date": "2026-07-01",
                "summary": "Recent market evidence for AI-assisted education.",
                "relevance_score": 0.9,
                "source_quality": "research_org",
                "stale": False,
            }
        ],
        evidence_chunks=[
            EvidenceChunk(
                source_id="framework-unit-economics",
                text="Unit economics should state CAC, LTV, margin, and payback assumptions.",
                score=0.91,
                metadata={
                    "file_name": "unit_economics.md",
                    "chunk_id": "unit-economics-1",
                    "quote": "Unit economics should state CAC, LTV, margin, and payback assumptions.",
                    "matched_sections": ["Financial Assumptions"],
                    "published_date": "2020-01-01",
                    "stale": True,
                },
            )
        ],
    )


def _proposal_json() -> str:
    """Return a valid ProposalDraft JSON payload for the fake Writer LLM."""
    proposal_data: dict[str, object] = {
        "title": "AI Tutor for MBA Students Proposal"
    }
    for title, field_name in zip(
        PROPOSAL_SECTION_TITLES,
        PROPOSAL_SECTION_FIELD_NAMES,
        strict=True,
    ):
        confidence = (
            "low"
            if title
            in {
                "Market Opportunity",
                "Competitor Analysis",
                "Go-to-Market Strategy",
                "Financial Assumptions",
            }
            else "medium"
        )
        proposal_data[field_name] = {
            "title": title,
            "content": (
                f"This {title} section uses only the supplied analysis packets. "
                + (
                    "Unit economics should disclose CAC, LTV, margin, and payback "
                    "assumptions [framework-unit-economics]."
                    if title == "Financial Assumptions"
                    else "Any uncertain statement remains an assumption that requires validation."
                )
            ),
            "key_claims": [
                (
                    "Unit economics inputs require explicit assumptions "
                    "[framework-unit-economics]."
                    if title == "Financial Assumptions"
                    else f"The {title} reasoning comes from supplied analysis."
                )
            ],
            "source_ids": (
                ["framework-unit-economics"]
                if title == "Financial Assumptions"
                else []
            ),
            "confidence": confidence,
        }
    return ProposalDraft.model_validate(proposal_data).model_dump_json()


class FakeWriterLLM:
    """Mock Writer LLM that records its prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class WriterAgentTests(unittest.TestCase):
    """Tests for Writer input validation, prompt boundaries, and output parsing."""

    def test_build_writer_prompt_includes_all_packets_and_fact_boundaries(self) -> None:
        """The prompt includes analysis, evidence, and source boundaries."""
        prompt = build_writer_prompt(_writer_input())

        self.assertIn('"research_analysis"', prompt)
        self.assertIn('"strategy_analysis"', prompt)
        self.assertIn('"finance_assumptions"', prompt)
        self.assertIn('"web_sources"', prompt)
        self.assertIn('"evidence_chunks"', prompt)
        self.assertIn("web-market-research", prompt)
        self.assertIn("framework-unit-economics", prompt)
        self.assertIn("Do not add facts", prompt)
        self.assertIn("exact source marker `[source_id]`", prompt)
        self.assertIn("confidence` to `low`", prompt)
        self.assertIn("metadata.stale", prompt)
        self.assertIn("state its publication date", prompt)
        self.assertIn("top-level `global_source_ids`", prompt)
        self.assertIn("`financial_assumptions.key_claims` to at most 8 items", prompt)

    def test_writer_agent_returns_validated_proposal_draft(self) -> None:
        """The Writer parses mock JSON into a logged, 13-section proposal."""
        events: list[AgentLogEvent] = []
        llm = FakeWriterLLM(_proposal_json())
        agent = WriterAgent(llm_client=llm, log_hook=events.append)

        proposal = agent.run(_writer_input())

        self.assertIsInstance(proposal, ProposalDraft)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(proposal.financial_assumptions.confidence, "low")
        self.assertEqual(
            proposal.financial_assumptions.source_ids,
            ["framework-unit-economics"],
        )
        self.assertEqual(
            proposal.global_source_ids,
            ["framework-unit-economics"],
        )
        self.assertEqual(proposal.market_opportunity.source_ids, [])
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_writer_rejects_missing_analysis_packet(self) -> None:
        """The Writer requires research, strategy, and finance packets."""
        invalid_input = _writer_input().model_dump()
        invalid_input.pop("finance_assumptions")

        with self.assertRaisesRegex(ValueError, "Invalid WriterInput"):
            build_writer_prompt(invalid_input)

    def test_writer_rejects_source_id_absent_from_evidence(self) -> None:
        """The Writer cannot invent a citation outside its evidence packet."""
        proposal_data = ProposalDraft.model_validate_json(_proposal_json()).model_dump()
        proposal_data["market_opportunity"]["source_ids"] = ["invented-source"]
        llm = FakeWriterLLM(ProposalDraft.model_validate(proposal_data).model_dump_json())
        agent = WriterAgent(llm_client=llm)

        with self.assertRaisesRegex(ValueError, "unknown source IDs"):
            agent.run(_writer_input())

    def test_writer_accepts_source_id_from_controlled_web_sources(self) -> None:
        """A web source passed through WriterInput belongs to the citation allowlist."""
        proposal_data = ProposalDraft.model_validate_json(_proposal_json()).model_dump()
        proposal_data["executive_summary"].update(
            content=(
                "The supplied market research supports the opportunity framing "
                "[web-market-research] while uncertainty remains explicit."
            ),
            key_claims=[
                "Market evidence supports the opportunity [web-market-research]."
            ],
            source_ids=["web-market-research"],
        )
        llm = FakeWriterLLM(
            ProposalDraft.model_validate(proposal_data).model_dump_json()
        )

        proposal = WriterAgent(llm_client=llm).run(_writer_input())

        self.assertIn("web-market-research", proposal.global_source_ids)


if __name__ == "__main__":
    unittest.main()
