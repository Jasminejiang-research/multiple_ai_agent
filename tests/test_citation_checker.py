"""Tests for deterministic proposal citation coverage checks."""

from __future__ import annotations

import unittest

from rag.citation_checker import (
    check_citations,
    check_claim_has_source,
    citation_coverage_score,
    extract_key_claims,
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
                "The TAM is €2 billion [market-2026].",
                "Acme is the leading competitor [competitors-2026].",
                "Demand is projected to grow by 15% annually.",
                "The product uses a modular architecture.",
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

    def test_uses_inline_content_citation_for_structured_claim(self) -> None:
        section = {
            "content": "Gross margin benchmark is 45% [finance-2026].",
            "key_claims": ["Gross margin benchmark is 45%"],
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


if __name__ == "__main__":
    unittest.main()
