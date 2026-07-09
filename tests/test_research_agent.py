"""Unit tests for the Research Agent (Sprint 7.3)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from agents.base import AgentLogEvent
from agents.research import ResearchAgent, build_research_prompt
from schemas.agent_outputs import ResearchAnalysis


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for Research Agent tests."""
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


def _research_analysis_json() -> str:
    """Return a valid ResearchAnalysis JSON payload for fake LLM responses."""
    analysis = ResearchAnalysis(
        analysis_summary=(
            "Research should treat AI education demand, MBA workflows, and substitutes "
            "as hypotheses until external sources are available."
        ),
        market_trends=[
            {
                "topic": "AI-assisted education workflows",
                "finding": "The brief suggests demand for personalized business case coaching.",
                "rationale": "The target customers need individualized feedback and practice support.",
                "confidence": "medium",
            }
        ],
        customer_notes=[
            {
                "topic": "MBA student coaching needs",
                "finding": "Students may value faster feedback on proposals and case analysis.",
                "rationale": "The stated problem is a lack of personalized business case coaching.",
                "confidence": "medium",
            }
        ],
        competitor_assumptions=[
            {
                "topic": "General AI and education substitutes",
                "finding": "General AI assistants and study platforms may act as substitutes.",
                "rationale": "The brief names AI education and business coaching as the product context.",
                "confidence": "low",
            }
        ],
        unsupported_claims=[
            {
                "claim": "The AI education market is growing quickly.",
                "why_unsupported": "No external source or dated market report was provided.",
                "needed_evidence": ["Recent market research report", "Education technology adoption data"],
            }
        ],
        needs_human_review=["Confirm which MBA programs or student segments matter most."],
    )
    return analysis.model_dump_json()


class FakeResearchLLM:
    """Mock Research LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class ResearchAgentTests(unittest.TestCase):
    """Tests for Research prompt construction and validated analysis output."""

    def test_build_research_prompt_includes_brief_and_output_boundaries(self) -> None:
        """The Research prompt contains user input and proposal-writing boundaries."""
        prompt = build_research_prompt(_complete_brief())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("market_trends", prompt)
        self.assertIn("customer_notes", prompt)
        self.assertIn("competitor_assumptions", prompt)
        self.assertIn("unsupported_claims", prompt)
        self.assertIn("Do not write a full business proposal", prompt)

    def test_research_agent_calls_mock_llm_and_returns_analysis(self) -> None:
        """The Research Agent parses fake LLM JSON into validated analysis."""
        events: list[AgentLogEvent] = []
        llm = FakeResearchLLM(_research_analysis_json())
        agent = ResearchAgent(llm_client=llm, log_hook=events.append)

        analysis = agent.run(_complete_brief())

        self.assertIsInstance(analysis, ResearchAnalysis)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(analysis.market_trends[0].topic, "AI-assisted education workflows")
        self.assertEqual(analysis.competitor_assumptions[0].confidence, "low")
        self.assertEqual(len(analysis.unsupported_claims), 1)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_research_analysis_rejects_full_proposal_fields(self) -> None:
        """Research output should not carry full proposal prose fields."""
        valid_payload = ResearchAnalysis.model_validate_json(_research_analysis_json()).model_dump()
        valid_payload["executive_summary"] = "This would be proposal writing, not research analysis."

        with self.assertRaises(ValidationError):
            ResearchAnalysis.model_validate(valid_payload)


if __name__ == "__main__":
    unittest.main()
