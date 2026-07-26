"""Tests for deterministic proposal citation coverage checks."""

from __future__ import annotations

import json
import unittest

from rag.citation_checker import (
    check_citations,
    check_claim_has_source,
    citation_coverage_score,
    collect_proposal_citation_failures,
    extract_key_claims,
    validate_proposal_citations,
    CitationValidationError,
)
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
    ProposalSection,
)


class CitationCheckerTests(unittest.TestCase):
    """Exercise claim extraction, source matching, and required claim classes."""

    def test_extracts_structured_key_claims_and_removes_duplicates(self) -> None:
        section = {
            "content": "Supporting prose.",
            "key_claims": [
                "The TAM is €2 billion.",
                "The TAM is €2 billion.",
                "  Demand is growing by 12% annually.  ",
                "",
            ],
            "source_ids": [],
        }

        self.assertEqual(
            extract_key_claims(section),
            [
                "The TAM is €2 billion.",
                "Demand is growing by 12% annually.",
            ],
        )

    def test_extracts_required_claims_from_plain_prose(self) -> None:
        claims = extract_key_claims(
            "The product is easy to configure. "
            "The addressable market is €2 billion [market-2026]. "
            "Demand is growing across Europe [trend-2026]."
        )

        self.assertEqual(len(claims), 2)
        self.assertIn("addressable market", claims[0])
        self.assertIn("Demand is growing", claims[1])

    def test_source_match_is_exact_and_rejects_unknown_citations(self) -> None:
        self.assertTrue(
            check_claim_has_source(
                "The market is growing [report-001].",
                ["report-001"],
            )
        )
        self.assertFalse(
            check_claim_has_source(
                "The market is growing [report-0010].",
                ["report-001"],
            )
        )
        self.assertFalse(
            check_claim_has_source(
                "The market is growing [unknown-source].",
                ["report-001"],
            )
        )

    def test_reports_coverage_for_market_competitor_and_trend_claims(self) -> None:
        section = {
            "title": "Market Opportunity",
            "content": (
                "The TAM is €2 billion [market-2026].\n"
                "Acme is the leading competitor [competitors-2026].\n"
                "Demand is projected to grow by 15% annually."
            ),
            "key_claims": [
                {
                    "text": "The TAM is €2 billion [market-2026].",
                    "claim_type": "market_size",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["market-2026"],
                    "content_anchor": "The TAM is €2 billion [market-2026].",
                },
                {
                    "text": "Acme is the leading competitor [competitors-2026].",
                    "claim_type": "competitor",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["competitors-2026"],
                    "content_anchor": (
                        "Acme is the leading competitor [competitors-2026]."
                    ),
                },
                {
                    "text": "Demand is projected to grow by 15% annually.",
                    "claim_type": "trend",
                    "evidence_status": "sourced_fact",
                    "source_ids": [],
                    "content_anchor": (
                        "Demand is projected to grow by 15% annually."
                    ),
                },
                {
                    "text": "The product uses a modular architecture.",
                    "claim_type": "product",
                    "evidence_status": "assumption",
                    "source_ids": [],
                    "content_anchor": (
                        "The product uses a modular architecture."
                    ),
                },
            ],
            "source_ids": ["market-2026", "competitors-2026"],
        }

        report = check_citations(section)

        self.assertEqual(report.required_claim_count, 3)
        self.assertEqual(report.cited_claim_count, 2)
        self.assertAlmostEqual(report.coverage_score, 2 / 3)
        self.assertEqual(citation_coverage_score(section), report.coverage_score)
        self.assertEqual(
            {claim_type for check in report.checks for claim_type in check.claim_types},
            {"market_size", "competitor", "trend"},
        )

    def test_requires_exact_markers_in_content_and_structured_claim(self) -> None:
        section = {
            "content": "Gross margin benchmark is 45% [finance-2026].",
            "key_claims": [
                {
                    "text": "Gross margin benchmark is 45% [finance-2026].",
                    "claim_type": "financial_benchmark",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["finance-2026"],
                    "content_anchor": (
                        "Gross margin benchmark is 45% [finance-2026]."
                    ),
                }
            ],
            "source_ids": ["finance-2026"],
        }

        report = check_citations(section)

        self.assertEqual(report.required_claim_count, 1)
        self.assertEqual(report.cited_claim_count, 1)
        self.assertEqual(report.coverage_score, 1.0)

    def test_no_required_claims_has_complete_coverage(self) -> None:
        section = {
            "content": "The product uses a modular architecture.",
            "key_claims": ["The product uses a modular architecture."],
            "source_ids": [],
        }

        self.assertEqual(citation_coverage_score(section), 1.0)

    def test_real_keyword_false_positives_are_evidence_gaps_not_citation_failures(
        self,
    ) -> None:
        """Assumption metadata, not keywords, controls citation enforcement."""
        section = ProposalSection.model_validate(
            {
                "title": "Financial Assumptions",
                "content": (
                    "Specific market data needs human review. No direct "
                    "competitors are currently identified. All financial figures "
                    "are assumptions, not forecasts."
                ),
                "key_claims": [
                    {
                        "text": "Specific market data needs human review.",
                        "claim_type": "market_size",
                        "evidence_status": "needs_validation",
                        "source_ids": [],
                        "content_anchor": (
                            "Specific market data needs human review."
                        ),
                    },
                    {
                        "text": "No direct competitors are currently identified.",
                        "claim_type": "competitor",
                        "evidence_status": "unsupported",
                        "source_ids": [],
                        "content_anchor": (
                            "No direct competitors are currently identified."
                        ),
                    },
                    {
                        "text": (
                            "All financial figures are assumptions, not forecasts."
                        ),
                        "claim_type": "financial_benchmark",
                        "evidence_status": "assumption",
                        "source_ids": [],
                        "content_anchor": (
                            "All financial figures are assumptions, not forecasts."
                        ),
                    },
                ],
                "source_ids": [],
                "confidence": "medium",
            }
        )

        report = check_citations(section)

        self.assertEqual(report.required_claim_count, 0)
        self.assertEqual(len(report.evidence_gaps), 3)
        self.assertEqual(section.confidence, "low")

    def test_collects_unknown_and_missing_markers_in_one_report(self) -> None:
        """One pass exposes every failure needed by a Revision patch."""
        proposal_data: dict[str, object] = {"title": "Citation test proposal"}
        for title, field_name in zip(
            PROPOSAL_SECTION_TITLES,
            PROPOSAL_SECTION_FIELD_NAMES,
            strict=True,
        ):
            proposal_data[field_name] = {
                "title": title,
                "content": (
                    f"This {title} section contains cautious planning assumptions "
                    "that require later validation."
                ),
                "key_claims": [
                    {
                        "text": f"The {title} plan requires validation.",
                        "claim_type": "general",
                        "evidence_status": "needs_validation",
                        "source_ids": [],
                        "content_anchor": (
                            f"This {title} section contains cautious planning "
                            "assumptions that require later validation."
                        ),
                    }
                ],
                "source_ids": [],
                "confidence": "low",
            }
        proposal_data["market_opportunity"] = {
            "title": "Market Opportunity",
            "content": (
                "The market is estimated at two billion [unknown-source]. "
                "A second sourced fact has no marker in its prose."
            ),
            "key_claims": [
                {
                    "text": (
                        "The market is estimated at two billion [unknown-source]."
                    ),
                    "claim_type": "market_size",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["unknown-source"],
                    "content_anchor": (
                        "The market is estimated at two billion [unknown-source]."
                    ),
                },
                {
                    "text": "A second sourced fact has no marker.",
                    "claim_type": "trend",
                    "evidence_status": "sourced_fact",
                    "source_ids": ["known-source"],
                    "content_anchor": (
                        "A second sourced fact has no marker in its prose."
                    ),
                },
            ],
            "source_ids": ["unknown-source", "known-source"],
            "confidence": "medium",
        }
        proposal = ProposalDraft.model_validate(proposal_data)

        failures = collect_proposal_citation_failures(
            proposal,
            allowed_source_ids=["known-source"],
        )

        self.assertEqual(len(failures), 2)
        self.assertIn("unknown_source_id", failures[0].reasons)
        self.assertIn("missing_content_citation", failures[1].reasons)
        self.assertIn("missing_key_claim_citation", failures[1].reasons)
        self.assertEqual(failures[1].available_source_ids, ["known-source"])

        with self.assertRaises(CitationValidationError) as caught:
            validate_proposal_citations(
                proposal,
                allowed_source_ids=["known-source"],
            )
        feedback = json.loads(caught.exception.validation_feedback())
        self.assertEqual(len(feedback), 2)
        self.assertEqual(
            set(feedback[0]),
            {
                "section",
                "claim_index",
                "claim_text",
                "claim_type",
                "evidence_status",
                "content_has_marker",
                "key_claim_has_marker",
                "available_source_ids",
                "unknown_source_ids",
                "reasons",
            },
        )


if __name__ == "__main__":
    unittest.main()
