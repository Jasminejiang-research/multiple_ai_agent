"""Unit tests for the Strategy Agent (Sprint 7.4)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from agents.base import AgentLogEvent
from agents.strategy import StrategyAgent, build_strategy_prompt
from schemas.agent_outputs import StrategyAnalysis


def _strategy_input() -> dict[str, object]:
    """A complete Strategy Agent input with brief and optional research context."""
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
        "research_analysis": {
            "analysis_summary": "Research context should be treated as hypotheses.",
            "unsupported_claims": ["Market growth needs external evidence."],
        },
    }


def _strategy_analysis_json() -> str:
    """Return a valid StrategyAnalysis JSON payload for fake LLM responses."""
    analysis = StrategyAnalysis(
        analysis_summary=(
            "Strategy should emphasize personalized coaching workflows while keeping "
            "market demand claims evidence-dependent."
        ),
        value_proposition=[
            {
                "topic": "Personalized MBA coaching",
                "recommendation": "Position the product around faster personalized proposal feedback.",
                "rationale": "The brief centers on students lacking tailored business case coaching.",
                "confidence": "medium",
            }
        ],
        business_model_logic=[
            {
                "topic": "Subscription and institutional licensing",
                "recommendation": "Use subscriptions for individuals and licensing for business schools.",
                "rationale": "The user brief names both monetization paths as the intended model.",
                "confidence": "medium",
            }
        ],
        gtm_strategy=[
            {
                "topic": "Campus-focused launch",
                "recommendation": "Start with MBA clubs, admissions coaches, and classroom pilots.",
                "rationale": "These channels align with the stated MBA student target customer.",
                "confidence": "low",
            }
        ],
        moat_hypotheses=[
            {
                "topic": "Workflow-specific feedback loops",
                "recommendation": "Explore defensibility through rubric data and specialized workflows.",
                "rationale": "Focused proposal coaching could improve with repeated student interactions.",
                "confidence": "low",
            }
        ],
        unsupported_market_data=[
            {
                "claim": "MBA students are rapidly adopting AI coaching tools.",
                "why_unsupported": "No external source or adoption dataset was provided.",
                "needed_evidence": ["Recent student survey", "Education technology adoption data"],
            }
        ],
        needs_human_review=["Confirm whether schools or individual students are the first buyer."],
    )
    return analysis.model_dump_json()


class FakeStrategyLLM:
    """Mock Strategy LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class StrategyAgentTests(unittest.TestCase):
    """Tests for Strategy prompt construction and validated analysis output."""

    def test_build_strategy_prompt_includes_input_and_strategy_boundaries(self) -> None:
        """The Strategy prompt contains input data and proposal-writing boundaries."""
        prompt = build_strategy_prompt(_strategy_input())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("value_proposition", prompt)
        self.assertIn("business_model_logic", prompt)
        self.assertIn("gtm_strategy", prompt)
        self.assertIn("moat_hypotheses", prompt)
        self.assertIn("unsupported_market_data", prompt)
        self.assertIn("Do not write a full business proposal", prompt)

    def test_strategy_agent_calls_mock_llm_and_returns_analysis(self) -> None:
        """The Strategy Agent parses fake LLM JSON into validated analysis."""
        events: list[AgentLogEvent] = []
        llm = FakeStrategyLLM(_strategy_analysis_json())
        agent = StrategyAgent(llm_client=llm, log_hook=events.append)

        analysis = agent.run(_strategy_input())

        self.assertIsInstance(analysis, StrategyAnalysis)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(analysis.value_proposition[0].topic, "Personalized MBA coaching")
        self.assertEqual(analysis.gtm_strategy[0].confidence, "low")
        self.assertEqual(len(analysis.unsupported_market_data), 1)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_strategy_analysis_rejects_full_proposal_fields(self) -> None:
        """Strategy output should not carry full proposal prose fields."""
        valid_payload = StrategyAnalysis.model_validate_json(_strategy_analysis_json()).model_dump()
        valid_payload["executive_summary"] = "This would be proposal writing, not strategy analysis."

        with self.assertRaises(ValidationError):
            StrategyAnalysis.model_validate(valid_payload)


if __name__ == "__main__":
    unittest.main()
