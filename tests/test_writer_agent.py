"""Unit tests for the Writer Agent (Sprint 7.6)."""

from __future__ import annotations

import unittest

from agents.base import AgentLogEvent
from agents.writer import WriterAgent, build_writer_prompt
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
                "Any uncertain statement remains an assumption that requires validation."
            ),
            "key_claims": [f"The {title} reasoning comes from supplied analysis."],
            "source_ids": [],
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
        """The prompt includes every packet and forbids new unverified facts."""
        prompt = build_writer_prompt(_writer_input())

        self.assertIn('"research_analysis"', prompt)
        self.assertIn('"strategy_analysis"', prompt)
        self.assertIn('"finance_assumptions"', prompt)
        self.assertIn("Do not add facts", prompt)
        self.assertIn("confidence` to `low`", prompt)

    def test_writer_agent_returns_validated_proposal_draft(self) -> None:
        """The Writer parses mock JSON into a logged, 13-section proposal."""
        events: list[AgentLogEvent] = []
        llm = FakeWriterLLM(_proposal_json())
        agent = WriterAgent(llm_client=llm, log_hook=events.append)

        proposal = agent.run(_writer_input())

        self.assertIsInstance(proposal, ProposalDraft)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(proposal.financial_assumptions.confidence, "low")
        self.assertEqual(proposal.market_opportunity.source_ids, [])
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_writer_rejects_missing_analysis_packet(self) -> None:
        """The Writer requires research, strategy, and finance packets."""
        invalid_input = _writer_input().model_dump()
        invalid_input.pop("finance_assumptions")

        with self.assertRaisesRegex(ValueError, "Invalid WriterInput"):
            build_writer_prompt(invalid_input)


if __name__ == "__main__":
    unittest.main()
