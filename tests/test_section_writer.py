"""Unit tests for the SectionWriter workflow node (Sprint 5.4)."""

from __future__ import annotations

import unittest

from schemas.workflow import PROPOSAL_SECTION_TITLES, ProposalOutline, SectionDrafts
from workflow.nodes import build_section_writer_prompt, section_writer_node
from workflow.state import WorkflowState


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for SectionWriter tests."""
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


def _outline() -> ProposalOutline:
    """Return a valid ProposalOutline object for SectionWriter inputs."""
    return ProposalOutline(
        proposal_title="AI Tutor for MBA Students Proposal",
        positioning_summary=(
            "Investor-style proposal for an AI coaching product serving MBA learners."
        ),
        target_reader="Seed investors",
        sections=[
            {
                "title": title,
                "objective": f"Plan the {title} section for a structured proposal.",
                "key_points": [
                    f"Explain the role of {title} using only brief-supported inputs."
                ],
                "evidence_needs": ["Validate factual claims in a later workflow node."],
            }
            for title in PROPOSAL_SECTION_TITLES
        ],
        key_assumptions=["Market facts need evidence before final writing."],
        needs_human_review=["Confirm the intended investor audience."],
    )


def _section_drafts_json() -> str:
    """Return a valid SectionDrafts JSON payload for fake LLM responses."""
    drafts = SectionDrafts(
        proposal_title="AI Tutor for MBA Students Proposal",
        sections=[
            {
                "title": title,
                "content": (
                    f"This draft covers the {title} section using only the user brief "
                    "and planner outline. Specific market or financial claims remain "
                    "framed as assumptions until evidence is added later."
                ),
                "key_claims": [
                    f"The {title} section depends on brief-supported positioning."
                ],
                "source_ids": [],
                "confidence": "medium",
            }
            for title in PROPOSAL_SECTION_TITLES
        ],
        writing_notes=["Market and financial claims need validation later."],
    )
    return drafts.model_dump_json()


class FakeSectionWriterLLM:
    """Mock SectionWriter LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class SectionWriterNodeTests(unittest.TestCase):
    """Tests for prompt construction and SectionWriter state updates."""

    def test_build_section_writer_prompt_includes_brief_outline_and_sections(self) -> None:
        """The writer prompt contains user input, outline, and fixed titles."""
        prompt = build_section_writer_prompt(_complete_brief(), _outline().model_dump())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("Seed investors", prompt)
        for title in PROPOSAL_SECTION_TITLES:
            self.assertIn(title, prompt)

    def test_section_writer_node_calls_mock_llm_and_saves_drafts(self) -> None:
        """The node parses fake LLM JSON and writes section drafts to state."""
        llm = FakeSectionWriterLLM(_section_drafts_json())
        state: WorkflowState = {
            "user_brief": _complete_brief(),
            "proposal_outline": _outline().model_dump(),
        }

        result = section_writer_node(state, llm_client=llm)

        self.assertEqual(result["current_step"], "section_writer")
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(
            result["section_drafts"]["proposal_title"],
            "AI Tutor for MBA Students Proposal",
        )
        self.assertEqual(len(result["section_drafts"]["sections"]), 13)
        self.assertEqual(
            result["section_drafts"]["sections"][0]["title"],
            "Executive Summary",
        )


if __name__ == "__main__":
    unittest.main()
