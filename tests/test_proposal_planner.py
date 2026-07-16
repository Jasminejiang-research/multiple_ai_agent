"""Unit tests for the ProposalPlanner workflow node (Sprint 5.3)."""

from __future__ import annotations

import unittest

from schemas.workflow import PROPOSAL_SECTION_TITLES, ProposalOutline
from workflow.nodes import build_planner_prompt, proposal_planner_node
from workflow.state import WorkflowState


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for planner tests."""
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


def _outline_json() -> str:
    """Return a valid ProposalOutline JSON payload for fake LLM responses."""
    outline = ProposalOutline(
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
    return outline.model_dump_json()


class FakePlannerLLM:
    """Mock planner LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class ProposalPlannerNodeTests(unittest.TestCase):
    """Tests for prompt construction and planner state updates."""

    def test_build_planner_prompt_includes_brief_and_required_sections(self) -> None:
        """The planner prompt contains user input and all fixed section titles."""
        prompt = build_planner_prompt(_complete_brief())

        self.assertIn("AI Tutor for MBA Students", prompt)
        for title in PROPOSAL_SECTION_TITLES:
            self.assertIn(title, prompt)

    def test_proposal_planner_node_calls_mock_llm_and_saves_outline(self) -> None:
        """The node parses fake LLM JSON and writes the outline to state."""
        llm = FakePlannerLLM(_outline_json())
        state: WorkflowState = {"user_brief": _complete_brief()}

        result = proposal_planner_node(state, llm_client=llm)

        self.assertEqual(result["current_step"], "proposal_planner")
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(
            result["proposal_outline"]["proposal_title"],
            "AI Tutor for MBA Students Proposal",
        )
        self.assertEqual(len(result["proposal_outline"]["sections"]), 13)


if __name__ == "__main__":
    unittest.main()
