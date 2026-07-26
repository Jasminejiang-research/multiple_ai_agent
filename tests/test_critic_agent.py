"""Unit tests for the Critic Agent (Sprint 7.7)."""

from __future__ import annotations

import unittest

from agents.base import AgentLogEvent
from agents.critic import CriticAgent, build_critic_prompt
from schemas.workflow import (
    CRITIQUE_MAX_ISSUES,
    CRITIQUE_MAX_MUST_FIX,
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


def _empty_critique_json() -> str:
    """Return a valid report with no model-generated issues."""
    return CritiqueReport(
        overall_score=9.0,
        issues=[],
        must_fix_before_export=[],
    ).model_dump_json()


def _sourced_claim(
    text: str,
    claim_type: str,
    *,
    source_ids: list[str] | None = None,
    content_anchor: str | None = None,
) -> dict[str, object]:
    return {
        "text": text,
        "claim_type": claim_type,
        "evidence_status": "sourced_fact",
        "source_ids": source_ids or [],
        "content_anchor": content_anchor or text,
    }


def _citation_proposal() -> ProposalDraft:
    """Return a draft containing the three Sprint 9.7 claim categories."""
    proposal_data = _proposal_draft().model_dump()
    proposal_data["executive_summary"].update(
        content=(
            "Customer adoption is projected to grow by 20% annually across the "
            "target segment, but this statement has no supporting citation."
        ),
        key_claims=[
            _sourced_claim(
                "Customer adoption is projected to grow by 20% annually.",
                "trend",
                content_anchor=(
                    "Customer adoption is projected to grow by 20% annually "
                    "across the target segment"
                ),
            )
        ],
    )
    proposal_data["market_opportunity"].update(
        content=(
            "The addressable market is estimated at €2 billion, but this market "
            "size statement currently has no supporting citation."
        ),
        key_claims=[
            _sourced_claim(
                "The addressable market is estimated at €2 billion.",
                "market_size",
                content_anchor=(
                    "The addressable market is estimated at €2 billion"
                ),
            )
        ],
    )
    proposal_data["competitor_analysis"].update(
        content=(
            "The competitor list includes Acme and Beta, but the named companies "
            "currently have no supporting citation."
        ),
        key_claims=[
            _sourced_claim(
                "The competitor list includes Acme and Beta.",
                "competitor",
                content_anchor=(
                    "The competitor list includes Acme and Beta"
                ),
            )
        ],
    )
    return ProposalDraft.model_validate(proposal_data)


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
            {
                "unsupported_market_claim",
                "financial_inconsistency",
                "weak_gtm",
            },
        )
        self.assertEqual(draft.model_dump(), before)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_critic_rejects_invalid_proposal_draft(self) -> None:
        """The Critic requires a complete, schema-valid ProposalDraft."""
        invalid_input = _proposal_draft().model_dump()
        invalid_input.pop("financial_assumptions")

        with self.assertRaisesRegex(ValueError, "Invalid ProposalDraft"):
            build_critic_prompt(invalid_input)

    def test_critic_marks_uncited_required_claims_high_severity(self) -> None:
        """Market-size, competitor, and trend claims are enforced deterministically."""
        agent = CriticAgent(llm_client=FakeCriticLLM(_empty_critique_json()))

        report = agent.run(_citation_proposal())

        enforced = [
            issue
            for issue in report.issues
            if issue.description.startswith("Citation enforcement:")
        ]
        self.assertEqual(len(enforced), 3)
        self.assertTrue(all(issue.severity == "high" for issue in enforced))
        descriptions = " ".join(issue.description for issue in enforced)
        self.assertIn("market_size", descriptions)
        self.assertIn("competitor", descriptions)
        self.assertIn("trend", descriptions)
        self.assertEqual(len(report.must_fix_before_export), 3)

    def test_critic_enforces_uncited_financial_benchmark(self) -> None:
        """Financial benchmark claims receive the same high-severity treatment."""
        proposal_data = _proposal_draft().model_dump()
        proposal_data["financial_assumptions"].update(
            content=(
                "The gross margin benchmark is 60 percent, but the statement "
                "currently has no supporting citation."
            ),
            key_claims=[
                _sourced_claim(
                    "The gross margin benchmark is 60 percent.",
                    "financial_benchmark",
                    content_anchor=(
                        "The gross margin benchmark is 60 percent"
                    ),
                )
            ],
            source_ids=[],
        )
        agent = CriticAgent(llm_client=FakeCriticLLM(_empty_critique_json()))

        report = agent.run(ProposalDraft.model_validate(proposal_data))

        financial_issues = [
            issue
            for issue in report.issues
            if "financial_benchmark" in issue.description
        ]
        self.assertEqual(len(financial_issues), 1)
        self.assertEqual(financial_issues[0].severity, "high")
        self.assertIn(
            financial_issues[0].description,
            report.must_fix_before_export,
        )

    def test_critic_marks_low_quality_citation_medium_severity(self) -> None:
        """A cited blog or unknown source is not treated as strong evidence."""
        proposal_data = _proposal_draft().model_dump()
        proposal_data["competitor_analysis"].update(
            content=(
                "The competitor list includes Acme and Beta [web-blog-1], based "
                "on a current comparison of alternatives in the target segment."
            ),
            key_claims=[
                _sourced_claim(
                    "The competitor list includes Acme and Beta [web-blog-1].",
                    "competitor",
                    source_ids=["web-blog-1"],
                    content_anchor=(
                        "The competitor list includes Acme and Beta "
                        "[web-blog-1]"
                    ),
                )
            ],
            source_ids=["web-blog-1"],
        )
        agent = CriticAgent(llm_client=FakeCriticLLM(_empty_critique_json()))

        report = agent.run(
            {
                "proposal_draft": proposal_data,
                "sources": [
                    {
                        "source_id": "web-blog-1",
                        "source_quality": "blog",
                    }
                ],
            }
        )

        enforced = [
            issue
            for issue in report.issues
            if issue.description.startswith("Citation enforcement:")
        ]
        self.assertEqual(len(enforced), 1)
        self.assertEqual(enforced[0].severity, "medium")
        self.assertIn("web-blog-1", enforced[0].description)
        self.assertEqual(report.must_fix_before_export, [])

    def test_critic_aggregates_overflow_within_revision_budget(self) -> None:
        """Deterministic citation findings cannot make the revision prompt unbounded."""
        initial = CritiqueReport(
            overall_score=4.0,
            issues=[
                {
                    "section": "General",
                    "severity": "medium",
                    "issue_type": "writing_quality",
                    "description": (
                        f"Distinct writing issue {index} requires a concrete edit."
                    ),
                    "suggested_fix": (
                        f"Apply focused writing correction {index} before export."
                    ),
                }
                for index in range(CRITIQUE_MAX_ISSUES)
            ],
            must_fix_before_export=[
                f"Resolve blocking issue {index}."
                for index in range(CRITIQUE_MAX_MUST_FIX)
            ],
        )
        agent = CriticAgent(llm_client=FakeCriticLLM(initial.model_dump_json()))

        report = agent.run(_citation_proposal())

        self.assertEqual(len(report.issues), CRITIQUE_MAX_ISSUES)
        self.assertEqual(
            len(report.must_fix_before_export),
            CRITIQUE_MAX_MUST_FIX,
        )
        self.assertTrue(
            any("aggregated" in issue.description for issue in report.issues)
        )
        self.assertIn("aggregated", report.must_fix_before_export[-1])


if __name__ == "__main__":
    unittest.main()
