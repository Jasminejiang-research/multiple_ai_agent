"""Unit tests for the Critic Agent (Sprint 7.7)."""

from __future__ import annotations

import unittest

from agents.base import AgentLogEvent
from agents.critic import CriticAgent, build_critic_prompt
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    CritiqueReport,
    ProposalDraft,
)


def _proposal_draft() -> ProposalDraft:
    """Return a complete proposal with reviewable evidence and assumption gaps."""
    proposal_data: dict[str, object] = {
        "title": "AI Tutor for MBA Students Proposal"
    }
    for title, field_name in zip(
        PROPOSAL_SECTION_TITLES,
        PROPOSAL_SECTION_FIELD_NAMES,
        strict=True,
    ):
        proposal_data[field_name] = {
            "title": title,
            "content": (
                f"The {title} section presents a preliminary assumption that requires "
                "validation before it can be treated as a supported fact."
            ),
            "key_claims": [f"The {title} claim is an unverified assumption."],
            "source_ids": [],
            "confidence": "low",
        }
    return ProposalDraft.model_validate(proposal_data)


def _critique_json() -> str:
    """Return a valid report covering all required Critic review areas."""
    return CritiqueReport(
        overall_score=5.5,
        issues=[
            {
                "section": "Market Opportunity",
                "severity": "high",
                "issue_type": "unsupported_market_claim",
                "description": "The market claim has no source id or supporting evidence.",
                "suggested_fix": "Remove the claim or add validated evidence and a source id.",
            },
            {
                "section": "Financial Assumptions",
                "severity": "high",
                "issue_type": "financial_inconsistency",
                "description": "The financial basis omits units and a defined time period.",
                "suggested_fix": "State the currency, unit, time period, and assumption basis.",
            },
            {
                "section": "Go-to-Market Strategy",
                "severity": "medium",
                "issue_type": "weak_gtm",
                "description": "The proposed channel lacks acquisition and validation logic.",
                "suggested_fix": "Define the target channel, experiment, and success measure.",
            },
        ],
        must_fix_before_export=[
            "Validate or remove the unsupported market claim.",
            "Clarify the financial assumption basis.",
        ],
    ).model_dump_json()


class FakeCriticLLM:
    """Mock Critic LLM that records its prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class CriticAgentTests(unittest.TestCase):
    """Tests for Critic input validation, boundaries, and structured output."""

    def test_build_critic_prompt_includes_draft_and_review_boundaries(self) -> None:
        """The prompt covers required checks and forbids proposal rewriting."""
        prompt = build_critic_prompt(_proposal_draft())

        self.assertIn('"market_opportunity"', prompt)
        self.assertIn("unsupported", prompt)
        self.assertIn("financial inconsistencies", prompt)
        self.assertIn("weak GTM", prompt)
        self.assertIn("Do not rewrite", prompt)

    def test_critic_agent_returns_validated_report_without_mutating_draft(self) -> None:
        """The Critic returns a logged report and leaves its input unchanged."""
        events: list[AgentLogEvent] = []
        llm = FakeCriticLLM(_critique_json())
        agent = CriticAgent(llm_client=llm, log_hook=events.append)
        draft = _proposal_draft()
        before = draft.model_dump()

        report = agent.run(draft)

        self.assertIsInstance(report, CritiqueReport)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(
            {issue.issue_type for issue in report.issues},
            {"unsupported_market_claim", "financial_inconsistency", "weak_gtm"},
        )
        self.assertEqual(draft.model_dump(), before)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_critic_rejects_invalid_proposal_draft(self) -> None:
        """The Critic requires a complete, schema-valid ProposalDraft."""
        invalid_input = _proposal_draft().model_dump()
        invalid_input.pop("financial_assumptions")

        with self.assertRaisesRegex(ValueError, "Invalid ProposalDraft"):
            build_critic_prompt(invalid_input)


if __name__ == "__main__":
    unittest.main()
