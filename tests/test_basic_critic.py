"""Unit tests for the BasicCritic workflow node (Sprint 5.6)."""

from __future__ import annotations

import unittest

from schemas.workflow import PROPOSAL_SECTION_TITLES, CritiqueReport, SectionDrafts
from workflow.nodes import (
    assemble_proposal_draft,
    basic_critic_node,
    build_basic_critic_prompt,
)
from workflow.state import WorkflowState


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for critic tests."""
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


def _proposal_draft_dict() -> dict:
    """Return a valid assembled ProposalDraft serialized for workflow state."""
    section_drafts = SectionDrafts(
        proposal_title="AI Tutor for MBA Students Proposal",
        sections=[
            {
                "title": title,
                "content": (
                    f"This draft covers the {title} section using validated inputs. "
                    "Factual and financial statements stay framed as assumptions "
                    "until later evidence and critique nodes run."
                ),
                "key_claims": [f"The {title} section is based on prior inputs."],
                "source_ids": [],
                "confidence": "medium",
            }
            for title in PROPOSAL_SECTION_TITLES
        ],
        writing_notes=["Evidence checks happen in a later workflow node."],
    )
    return assemble_proposal_draft(section_drafts).model_dump()


def _critique_json() -> str:
    """Return a valid CritiqueReport JSON payload for fake LLM responses."""
    report = CritiqueReport(
        overall_score=6.5,
        issues=[
            {
                "section": "Financial Assumptions",
                "severity": "high",
                "issue_type": "financial_inconsistency",
                "description": "Revenue assumptions omit units and a stated basis.",
                "suggested_fix": "State currency, time horizon, and pricing basis.",
            },
            {
                "section": "Market Opportunity",
                "severity": "medium",
                "issue_type": "missing_evidence",
                "description": "Market size claim has no supporting source id.",
                "suggested_fix": "Mark as an assumption or add a cited source later.",
            },
        ],
        must_fix_before_export=[
            "Clarify financial assumption units before export.",
        ],
    )
    return report.model_dump_json()


class FakeBasicCriticLLM:
    """Mock critic LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class BasicCriticNodeTests(unittest.TestCase):
    """Tests for prompt construction and critic state updates."""

    def test_build_basic_critic_prompt_includes_brief_and_draft(self) -> None:
        """The critic prompt contains the brief and the assembled draft."""
        prompt = build_basic_critic_prompt(_complete_brief(), _proposal_draft_dict())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("Financial Assumptions", prompt)
        self.assertIn("Proposal Draft JSON", prompt)

    def test_basic_critic_node_calls_mock_llm_and_saves_report(self) -> None:
        """The node parses fake LLM JSON and writes the critique to state."""
        llm = FakeBasicCriticLLM(_critique_json())
        state: WorkflowState = {
            "user_brief": _complete_brief(),
            "proposal_draft": _proposal_draft_dict(),
        }

        result = basic_critic_node(state, llm_client=llm)

        self.assertEqual(result["current_step"], "basic_critic")
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(result["critique_report"]["overall_score"], 6.5)
        self.assertEqual(len(result["critique_report"]["issues"]), 2)
        self.assertEqual(
            result["critique_report"]["must_fix_before_export"],
            ["Clarify financial assumption units before export."],
        )

    def test_basic_critic_node_requires_proposal_draft(self) -> None:
        """The node raises a clear error when no proposal draft is present."""
        llm = FakeBasicCriticLLM(_critique_json())
        state: WorkflowState = {"user_brief": _complete_brief()}

        with self.assertRaises(ValueError):
            basic_critic_node(state, llm_client=llm)


if __name__ == "__main__":
    unittest.main()
