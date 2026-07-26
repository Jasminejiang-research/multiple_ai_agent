"""Unit tests for the Finance Agent (Sprint 7.5)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from agents.base import AgentLogEvent
from agents.finance import FinanceAgent, build_finance_prompt
from schemas.agent_outputs import FinanceAssumptions


def _finance_input() -> dict[str, object]:
    """A complete Finance Agent input with brief and optional strategy context."""
    return {
        "user_brief": {
            "company_or_product_name": "AI Tutor for MBA Students",
            "industry": "EdTech / AI Education",
            "target_customer": "MBA students and business school applicants",
            "problem": "Students lack personalized business case coaching.",
            "solution": "An AI-driven proposal and case coaching platform.",
            "business_model": "Subscription plus institutional licensing",
            "geography": "US / North America",
            "proposal_goal": "investor",
        },
        "strategy_analysis": {
            "analysis_summary": "Strategy context should be treated as hypotheses.",
            "business_model_logic": ["Subscriptions and institutional licensing are possible paths."],
        },
    }


def _finance_assumptions_json() -> str:
    """Return a valid FinanceAssumptions JSON payload for fake LLM responses."""
    assumptions = FinanceAssumptions(
        analysis_summary=(
            "Finance assumptions should focus on subscription revenue, delivery costs, "
            "and uncertain school licensing dynamics."
        ),
        revenue_assumptions=[
            {
                "topic": "Subscription revenue",
                "assumption": "Individual subscriptions could be one revenue path if students pay directly.",
                "rationale": "The brief names subscription as part of the intended business model.",
                "confidence": "medium",
                "needs_validation": ["Willingness-to-pay research", "Pricing tests"],
            }
        ],
        cost_assumptions=[
            {
                "topic": "AI delivery cost",
                "assumption": "Usage-based AI inference costs could scale with coaching session volume.",
                "rationale": "The solution depends on AI-driven feedback and coaching workflows.",
                "confidence": "medium",
                "needs_validation": ["Model cost estimates", "Expected usage per student"],
            }
        ],
        unit_economics_assumptions=[
            {
                "topic": "Payback sensitivity",
                "assumption": "CAC payback would depend on pricing, conversion, retention, and acquisition channel mix.",
                "rationale": "The target buyers may include both individuals and institutions.",
                "confidence": "low",
                "needs_validation": ["Pilot conversion data", "Channel CAC benchmarks"],
            }
        ],
        break_even_discussion=(
            "Break-even would depend on validated pricing, active user volume, AI delivery cost per session, "
            "support load, and whether institutional contracts reduce acquisition costs."
        ),
        assumption_notice="All financial figures are assumptions for planning discussion, not forecasts.",
        unsupported_financial_claims=[
            {
                "claim": "The product can reach break-even within one year.",
                "why_unsupported": "No pricing, CAC, retention, margin, or sales cycle evidence was provided.",
                "needed_evidence": ["Pilot revenue data", "Cost model", "Sales cycle assumptions"],
            }
        ],
        needs_human_review=["Confirm whether individual students or institutions are the first buyer."],
    )
    return assumptions.model_dump_json()


class FakeFinanceLLM:
    """Mock Finance LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class FinanceAgentTests(unittest.TestCase):
    """Tests for Finance prompt construction and validated assumptions output."""

    def test_build_finance_prompt_includes_input_and_finance_boundaries(self) -> None:
        """The Finance prompt contains input data and forecast boundaries."""
        prompt = build_finance_prompt(_finance_input())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("revenue_assumptions", prompt)
        self.assertIn("cost_assumptions", prompt)
        self.assertIn("unit_economics_assumptions", prompt)
        self.assertIn("break_even_discussion", prompt)
        self.assertIn("not forecasts", prompt)
        self.assertIn("Do not write a full business proposal", prompt)
        self.assertIn("`needs_human_review`; keep the list to at most 8 items", prompt)

    def test_finance_agent_calls_mock_llm_and_returns_assumptions(self) -> None:
        """The Finance Agent parses fake LLM JSON into validated assumptions."""
        events: list[AgentLogEvent] = []
        llm = FakeFinanceLLM(_finance_assumptions_json())
        agent = FinanceAgent(llm_client=llm, log_hook=events.append)

        assumptions = agent.run(_finance_input())

        self.assertIsInstance(assumptions, FinanceAssumptions)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(assumptions.revenue_assumptions[0].topic, "Subscription revenue")
        self.assertEqual(assumptions.unit_economics_assumptions[0].confidence, "low")
        self.assertEqual(len(assumptions.unsupported_financial_claims), 1)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_finance_assumptions_rejects_full_proposal_fields(self) -> None:
        """Finance output should not carry full proposal prose fields."""
        valid_payload = FinanceAssumptions.model_validate_json(
            _finance_assumptions_json()
        ).model_dump()
        valid_payload["executive_summary"] = "This would be proposal writing, not finance analysis."

        with self.assertRaises(ValidationError):
            FinanceAssumptions.model_validate(valid_payload)

    def test_finance_assumptions_require_forecast_disclaimer(self) -> None:
        """Finance output must explicitly say figures are assumptions, not forecasts."""
        valid_payload = FinanceAssumptions.model_validate_json(
            _finance_assumptions_json()
        ).model_dump()
        valid_payload["assumption_notice"] = "These are planning notes for discussion."

        with self.assertRaises(ValidationError):
            FinanceAssumptions.model_validate(valid_payload)


if __name__ == "__main__":
    unittest.main()
