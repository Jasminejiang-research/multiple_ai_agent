"""Unit tests for the Revision workflow node (Sprint 5.7)."""

from __future__ import annotations

import unittest

from schemas.workflow import (
    PROPOSAL_SECTION_TITLES,
    CritiqueReport,
    RevisedProposal,
    SectionDrafts,
)
from workflow.nodes import (
    assemble_proposal_draft,
    build_revision_prompt,
    revision_node,
)
from workflow.state import WorkflowState


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


def _critique_report_dict() -> dict:
    """Return a valid CritiqueReport serialized for workflow state."""
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
        ],
        must_fix_before_export=["Clarify financial assumption units before export."],
    )
    return report.model_dump()


def _revised_proposal_json() -> str:
    """Return a valid RevisedProposal JSON payload for fake LLM responses."""
    draft = _proposal_draft_dict()
    draft["financial_assumptions"]["content"] = (
        "Financial assumptions are stated as draft planning assumptions in USD "
        "over a 12-month horizon, with pricing and cost basis to be validated "
        "before export."
    )
    draft["financial_assumptions"]["confidence"] = "low"
    revised = RevisedProposal(
        proposal=draft,
        applied_critique_summary=[
            "Clarified Financial Assumptions with currency, horizon, and basis."
        ],
        unresolved_issues=[
            "Financial assumptions still need external evidence before export."
        ],
    )
    return revised.model_dump_json()


class FakeRevisionLLM:
    """Mock Revision LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class RevisionNodeTests(unittest.TestCase):
    """Tests for prompt construction and revision state updates."""

    def test_build_revision_prompt_includes_draft_and_critique(self) -> None:
        """The revision prompt contains the draft and critique report."""
        prompt = build_revision_prompt(_proposal_draft_dict(), _critique_report_dict())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("Critique Report JSON", prompt)
        self.assertIn("Revenue assumptions omit units", prompt)

    def test_revision_node_calls_mock_llm_and_saves_revised_proposal(self) -> None:
        """The node parses fake LLM JSON and writes the revised proposal."""
        llm = FakeRevisionLLM(_revised_proposal_json())
        state: WorkflowState = {
            "proposal_draft": _proposal_draft_dict(),
            "critique_report": _critique_report_dict(),
        }

        result = revision_node(state, llm_client=llm)

        self.assertEqual(result["current_step"], "revision")
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(
            result["revised_proposal"]["proposal"]["title"],
            "AI Tutor for MBA Students Proposal",
        )
        self.assertEqual(
            result["revised_proposal"]["proposal"]["financial_assumptions"][
                "confidence"
            ],
            "low",
        )
        self.assertEqual(len(result["revised_proposal"]["unresolved_issues"]), 1)

    def test_revision_node_requires_draft_and_critique(self) -> None:
        """The node raises clear errors when required state is missing."""
        llm = FakeRevisionLLM(_revised_proposal_json())

        with self.assertRaises(ValueError):
            revision_node({"critique_report": _critique_report_dict()}, llm_client=llm)

        with self.assertRaises(ValueError):
            revision_node({"proposal_draft": _proposal_draft_dict()}, llm_client=llm)


if __name__ == "__main__":
    unittest.main()
