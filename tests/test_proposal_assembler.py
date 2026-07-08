"""Unit tests for the ProposalAssembler workflow node (Sprint 5.5)."""

from __future__ import annotations

import unittest

from schemas.workflow import PROPOSAL_SECTION_TITLES, SectionDrafts
from workflow.nodes import (
    assemble_proposal_draft,
    proposal_assembler_node,
    render_proposal_preview,
)
from workflow.state import WorkflowState


def _section_drafts() -> SectionDrafts:
    """Return valid SectionDrafts covering all 13 required proposal sections."""
    return SectionDrafts(
        proposal_title="AI Tutor for MBA Students Proposal",
        sections=[
            {
                "title": title,
                "content": (
                    f"This assembled draft covers the {title} section using validated "
                    "SectionWriter output. It keeps factual and financial statements "
                    "framed as assumptions until later evidence and critique nodes run."
                ),
                "key_claims": [
                    f"The {title} section is based on prior workflow inputs."
                ],
                "source_ids": [],
                "confidence": "medium",
            }
            for title in PROPOSAL_SECTION_TITLES
        ],
        writing_notes=["Evidence checks happen in a later workflow node."],
    )


class ProposalAssemblerNodeTests(unittest.TestCase):
    """Tests for deterministic assembly and Markdown preview rendering."""

    def test_assemble_proposal_draft_maps_all_sections_to_fields(self) -> None:
        """The assembler converts SectionDrafts into fixed ProposalDraft fields."""
        proposal_draft = assemble_proposal_draft(_section_drafts())

        self.assertEqual(
            proposal_draft.title,
            "AI Tutor for MBA Students Proposal",
        )
        self.assertEqual(
            proposal_draft.executive_summary.title,
            "Executive Summary",
        )
        self.assertEqual(proposal_draft.appendix.title, "Appendix")

    def test_render_proposal_preview_includes_all_sections_and_metadata(self) -> None:
        """The Markdown preview contains every fixed heading and confidence."""
        proposal_draft = assemble_proposal_draft(_section_drafts())

        preview = render_proposal_preview(proposal_draft)

        self.assertIn("# AI Tutor for MBA Students Proposal", preview)
        self.assertEqual(preview.count("**Confidence:** medium"), 13)
        for title in PROPOSAL_SECTION_TITLES:
            self.assertIn(f"## {title}", preview)

    def test_proposal_assembler_node_saves_draft_and_preview(self) -> None:
        """The node writes ProposalDraft and Markdown preview to workflow state."""
        state: WorkflowState = {"section_drafts": _section_drafts().model_dump()}

        result = proposal_assembler_node(state)

        self.assertEqual(result["current_step"], "proposal_assembler")
        self.assertEqual(
            result["proposal_draft"]["title"],
            "AI Tutor for MBA Students Proposal",
        )
        self.assertIn("## Executive Summary", result["markdown_preview"])
        self.assertIn("## Appendix", result["markdown_preview"])

    def test_proposal_assembler_rejects_missing_sections(self) -> None:
        """A draft payload without all 13 sections is rejected before assembly."""
        invalid_payload = _section_drafts().model_dump()
        invalid_payload["sections"] = invalid_payload["sections"][:-1]

        with self.assertRaises(ValueError):
            assemble_proposal_draft(invalid_payload)


if __name__ == "__main__":
    unittest.main()
