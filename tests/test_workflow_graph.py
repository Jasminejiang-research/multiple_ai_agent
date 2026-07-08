"""End-to-end mock tests for the assembled proposal workflow graph."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from schemas.workflow import (
    PROPOSAL_SECTION_TITLES,
    CritiqueReport,
    ProposalOutline,
    RevisedProposal,
    SectionDrafts,
)
from workflow.graph import build_proposal_workflow_graph
from workflow.nodes import assemble_proposal_draft, export_node
from workflow.state import WorkflowState


def _complete_brief() -> dict[str, str]:
    """Return a valid brief for full workflow execution."""
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
    """Return valid planner JSON for a fake LLM response."""
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


def _section_drafts() -> SectionDrafts:
    """Return valid section drafts for all 13 fixed proposal sections."""
    return SectionDrafts(
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


def _critique_json() -> str:
    """Return valid critic JSON for a fake LLM response."""
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
    return report.model_dump_json()


def _revised_proposal_json() -> str:
    """Return valid revision JSON for a fake LLM response."""
    draft = assemble_proposal_draft(_section_drafts()).model_dump()
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


class FakeJsonLLM:
    """Mock LLM adapter that records prompts and returns canned JSON."""

    def __init__(self, response: str) -> None:
        """Store the response returned by ``generate_json``."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned JSON response."""
        self.prompts.append(prompt)
        return self.response


class ProposalWorkflowGraphTests(unittest.TestCase):
    """Tests for graph routing and full mock workflow execution."""

    def test_export_node_writes_final_markdown_without_llm(self) -> None:
        """The standalone export node saves non-empty Markdown from state."""
        revised = RevisedProposal.model_validate_json(_revised_proposal_json())
        state: WorkflowState = {
            "run_id": "export-node-test",
            "user_brief": _complete_brief(),
            "revised_proposal": revised.model_dump(),
        }

        with TemporaryDirectory() as temp_dir:
            result = export_node(state, output_dir=Path(temp_dir))

            output_path = Path(result["output_path"])
            self.assertEqual(result["current_step"], "export")
            self.assertTrue(output_path.is_file())
            self.assertIn("ai_tutor_for_mba_students", output_path.name)
            self.assertIn("## Executive Summary", result["final_markdown"])
            self.assertEqual(output_path.read_text(encoding="utf-8"), result["final_markdown"])

    def test_graph_runs_full_mock_workflow_and_exports_markdown(self) -> None:
        """A complete brief flows through every node and writes Markdown."""
        planner_llm = FakeJsonLLM(_outline_json())
        writer_llm = FakeJsonLLM(_section_drafts().model_dump_json())
        critic_llm = FakeJsonLLM(_critique_json())
        revision_llm = FakeJsonLLM(_revised_proposal_json())

        with TemporaryDirectory() as temp_dir:
            graph = build_proposal_workflow_graph(
                planner_llm=planner_llm,
                section_writer_llm=writer_llm,
                critic_llm=critic_llm,
                revision_llm=revision_llm,
                output_dir=Path(temp_dir),
            )
            state: WorkflowState = {
                "run_id": "test-run-001",
                "user_brief": _complete_brief(),
            }

            result = graph.invoke(state)

            self.assertEqual(result["current_step"], "export")
            self.assertEqual(result["missing_info"], [])
            self.assertIn("## Executive Summary", result["final_markdown"])
            self.assertIn("## Appendix", result["final_markdown"])
            self.assertTrue(Path(result["output_path"]).is_file())
            self.assertEqual(len(planner_llm.prompts), 1)
            self.assertEqual(len(writer_llm.prompts), 1)
            self.assertEqual(len(critic_llm.prompts), 1)
            self.assertEqual(len(revision_llm.prompts), 1)

    def test_graph_stops_before_llm_nodes_when_missing_info_exists(self) -> None:
        """Incomplete input follows the missing-info branch without LLM calls."""
        planner_llm = FakeJsonLLM(_outline_json())
        graph = build_proposal_workflow_graph(planner_llm=planner_llm)
        brief = _complete_brief()
        del brief["problem"]
        state: WorkflowState = {"user_brief": brief}

        result = graph.invoke(state)

        self.assertEqual(result["current_step"], "input_validator")
        self.assertIn("Missing required field: problem", result["missing_info"])
        self.assertNotIn("proposal_outline", result)
        self.assertEqual(planner_llm.prompts, [])


if __name__ == "__main__":
    unittest.main()
