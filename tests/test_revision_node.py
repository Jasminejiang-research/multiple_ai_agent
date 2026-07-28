"""Unit tests for the Revision workflow node (Sprint 5.7)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from schemas.workflow import (
    PROPOSAL_SECTION_TITLES,
    CritiqueReport,
    RevisedProposal,
    RevisedProposalPatch,
    SectionDrafts,
)
from workflow.nodes import (
    assemble_proposal_draft,
    build_revision_prompt,
    export_node,
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
                "key_claims": (
                    []
                    if title == "Competitor Analysis"
                    else [f"The {title} section is based on prior inputs."]
                ),
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


class ValidatorAwareRevisionLLM(FakeRevisionLLM):
    """Exercise the production adapter's dynamic semantic-validation path."""

    def __init__(self, response: str) -> None:
        super().__init__(response)
        self.validator_calls = 0

    def generate_json_validated(self, prompt: str, output_validator: object) -> str:
        self.prompts.append(prompt)
        self.validator_calls += 1
        candidate = RevisedProposal.model_validate_json(self.response)
        assert callable(output_validator)
        output_validator(candidate)
        return self.response


class SequenceRevisionLLM:
    """Return one full revision followed by one failed-section patch."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses[len(self.prompts) - 1]


class BatchedRevisionLLM:
    """Return the requested subset of one complete valid revision."""

    def __init__(self, response: str) -> None:
        self.revision = RevisedProposal.model_validate_json(response)
        self.calls: list[tuple[str, type]] = []

    def generate_json_for_schema_once(self, prompt: str, schema: type) -> str:
        self.calls.append((prompt, schema))
        proposal_payload = self.revision.proposal.model_dump()
        payload = {
            field_name: proposal_payload[field_name]
            for field_name in schema.model_fields
            if field_name in proposal_payload
        }
        for metadata_field in (
            "applied_critique_summary",
            "unresolved_issues",
        ):
            if metadata_field in schema.model_fields:
                payload[metadata_field] = getattr(
                    self.revision,
                    metadata_field,
                )
        return schema.model_validate(payload).model_dump_json()


class RevisionNodeTests(unittest.TestCase):
    """Tests for prompt construction and revision state updates."""

    def test_build_revision_prompt_includes_draft_and_critique(self) -> None:
        """The revision prompt contains the draft and critique report."""
        prompt = build_revision_prompt(
            _proposal_draft_dict(),
            _critique_report_dict(),
            ["allowed-source"],
        )

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("Critique Report JSON", prompt)
        self.assertIn("Revenue assumptions omit units", prompt)
        self.assertIn("Allowed Source IDs JSON", prompt)
        self.assertIn("allowed-source", prompt)
        self.assertIn("both", prompt)
        self.assertIn("claim's `text`", prompt)
        self.assertIn("Do not automatically insert", prompt)
        self.assertIn("Compact Evidence Mapping JSON", prompt)

    def test_revision_node_calls_mock_llm_and_saves_revised_proposal(self) -> None:
        """The node parses fake LLM JSON and writes the revised proposal."""
        llm = ValidatorAwareRevisionLLM(_revised_proposal_json())
        state: WorkflowState = {
            "proposal_draft": _proposal_draft_dict(),
            "critique_report": _critique_report_dict(),
        }

        result = revision_node(state, llm_client=llm)

        self.assertEqual(result["current_step"], "revision")
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(llm.validator_calls, 0)
        self.assertFalse(result["needs_citation_review"])
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

    def test_revision_uses_four_generation_batches_when_supported(self) -> None:
        llm = BatchedRevisionLLM(_revised_proposal_json())

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
            },
            llm_client=llm,
        )

        self.assertEqual(len(llm.calls), 4)
        self.assertEqual(
            [schema.__name__ for _, schema in llm.calls],
            [
                "RevisedProposalBatch1",
                "RevisedProposalBatch2",
                "RevisedProposalBatch3",
                "RevisedProposalBatch4",
            ],
        )
        self.assertTrue(
            all(
                "Authoritative Revision Batch Override" in prompt
                for prompt, _ in llm.calls
            )
        )
        self.assertFalse(result["needs_citation_review"])

    def test_revision_rejects_source_id_outside_complete_allowlist(self) -> None:
        """A revised proposal cannot invent a source absent from RAG/Web/draft."""
        payload = json.loads(_revised_proposal_json())
        payload["proposal"]["market_opportunity"].update(
            content=(
                "The market-size framing is an assumption supported by an "
                "invented reference [invented-source]."
            ),
            key_claims=[
                "The market size remains an assumption [invented-source]."
            ],
            source_ids=["invented-source"],
        )
        llm = FakeRevisionLLM(json.dumps(payload))

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
            },
            llm_client=llm,
        )

        self.assertTrue(result["needs_citation_review"])
        self.assertEqual(len(llm.prompts), 2)
        self.assertIn(
            "unknown_source_id",
            result["citation_failures"][0]["reasons"],
        )

    def test_revision_rejects_source_sensitive_claim_without_inline_citation(self) -> None:
        """Post-revision citation enforcement runs before export."""
        payload = json.loads(_revised_proposal_json())
        payload["proposal"]["competitor_analysis"].update(
            content=(
                "Competitor Alpha is presented as a possible alternative, but "
                "the statement still requires supporting evidence."
            ),
            key_claims=[
                {
                    "text": "Competitor Alpha is a possible alternative.",
                    "claim_type": "competitor",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["web-competitor"],
                    "content_anchor": (
                        "Competitor Alpha is presented as a possible alternative"
                    ),
                }
            ],
            source_ids=[],
        )
        llm = FakeRevisionLLM(json.dumps(payload))

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
                "web_sources": [
                    {
                        "source_id": "web-competitor",
                        "title": "Competitor evidence",
                        "summary": "Competitor Alpha is a possible alternative.",
                        "relevance_score": 0.9,
                    }
                ],
            },
            llm_client=llm,
        )

        self.assertTrue(result["needs_citation_review"])
        self.assertIn(
            "missing_content_citation",
            result["citation_failures"][0]["reasons"],
        )
        self.assertIn(
            "missing_key_claim_citation",
            result["citation_failures"][0]["reasons"],
        )
        with TemporaryDirectory() as output_dir:
            exported = export_node(
                {**result, "run_id": "citation-review"},
                output_dir=Path(output_dir),
            )
            self.assertIn(
                "# ⚠ Needs Citation Review",
                exported["final_markdown"],
            )
            self.assertTrue(Path(exported["output_path"]).is_file())

    def test_second_call_patches_only_failed_sections(self) -> None:
        """A citation failure preserves all first-pass sections except its patch."""
        first_payload = json.loads(_revised_proposal_json())
        first_payload["proposal"]["market_opportunity"].update(
            content=(
                "The directly supplied evidence estimates a two-billion market."
            ),
            key_claims=[
                {
                    "text": "The evidence estimates a two-billion market.",
                    "claim_type": "market_size",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["web-market"],
                    "content_anchor": (
                        "The directly supplied evidence estimates a two-billion "
                        "market."
                    ),
                }
            ],
            source_ids=["web-market"],
        )
        replacement = dict(first_payload["proposal"]["market_opportunity"])
        replacement.update(
            content=(
                "The directly supplied evidence estimates a two-billion market "
                "[web-market]."
            ),
            key_claims=[
                {
                    "text": (
                        "The evidence estimates a two-billion market [web-market]."
                    ),
                    "claim_type": "market_size",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["web-market"],
                    "content_anchor": (
                        "The directly supplied evidence estimates a two-billion "
                        "market [web-market]."
                    ),
                }
            ],
        )
        patch = RevisedProposalPatch.model_validate(
            {
                "sections": [
                    {
                        "section": "market_opportunity",
                        "replacement": replacement,
                    }
                ]
            }
        )
        llm = SequenceRevisionLLM(
            [json.dumps(first_payload), patch.model_dump_json()]
        )

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
                "web_sources": [
                    {
                        "source_id": "web-market",
                        "title": "Market report",
                        "summary": "The addressable market is two billion.",
                        "relevance_score": 0.9,
                    }
                ],
            },
            llm_client=llm,
        )

        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Complete CitationFailure JSON", llm.prompts[1])
        self.assertIn('"market_opportunity"', llm.prompts[1])
        self.assertFalse(result["needs_citation_review"])
        self.assertIn(
            "[web-market]",
            result["revised_proposal"]["proposal"]["market_opportunity"][
                "content"
            ],
        )
        self.assertEqual(
            result["revised_proposal"]["proposal"]["problem"],
            first_payload["proposal"]["problem"],
        )

    def test_schema_correction_is_limited_to_two_full_calls(self) -> None:
        llm = SequenceRevisionLLM(["{}", _revised_proposal_json()])

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
            },
            llm_client=llm,
        )

        self.assertEqual(len(llm.prompts), 2)
        self.assertIn("Final Full-Output Correction", llm.prompts[1])
        self.assertFalse(result["needs_citation_review"])

    def test_persistent_schema_failure_preserves_review_draft_after_two_calls(
        self,
    ) -> None:
        llm = SequenceRevisionLLM(["{}", "{}"])

        result = revision_node(
            {
                "proposal_draft": _proposal_draft_dict(),
                "critique_report": _critique_report_dict(),
            },
            llm_client=llm,
        )

        self.assertEqual(len(llm.prompts), 2)
        self.assertTrue(result["needs_citation_review"])
        self.assertEqual(
            result["revised_proposal"]["proposal"]["title"],
            "AI Tutor for MBA Students Proposal",
        )

    def test_revision_node_requires_draft_and_critique(self) -> None:
        """The node raises clear errors when required state is missing."""
        llm = FakeRevisionLLM(_revised_proposal_json())

        with self.assertRaises(ValueError):
            revision_node({"critique_report": _critique_report_dict()}, llm_client=llm)

        with self.assertRaises(ValueError):
            revision_node({"proposal_draft": _proposal_draft_dict()}, llm_client=llm)


if __name__ == "__main__":
    unittest.main()
