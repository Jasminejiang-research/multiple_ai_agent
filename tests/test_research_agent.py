"""Unit tests for the Research Agent (Sprint 7.3)."""

from __future__ import annotations

import unittest

import requests
from pydantic import ValidationError

from agents.base import AgentLogEvent
from agents.research import ResearchAgent, build_research_prompt
from schemas.agent_outputs import ResearchAnalysis
from schemas.source import SourceQuality, WebSearchResult
from tools.tavily_search import (
    WebSearchConfigurationError,
    WebSearchProviderError,
    WebSearchRateLimitError,
)


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for Research Agent tests."""
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


def _research_analysis_json() -> str:
    """Return a valid ResearchAnalysis JSON payload for fake LLM responses."""
    analysis = ResearchAnalysis(
        analysis_summary=(
            "Research should treat AI education demand, MBA workflows, and substitutes "
            "as hypotheses until external sources are available."
        ),
        market_trends=[
            {
                "topic": "AI-assisted education workflows",
                "finding": "The brief suggests demand for personalized business case coaching.",
                "rationale": "The target customers need individualized feedback and practice support.",
                "confidence": "medium",
            }
        ],
        customer_notes=[
            {
                "topic": "MBA student coaching needs",
                "finding": "Students may value faster feedback on proposals and case analysis.",
                "rationale": "The stated problem is a lack of personalized business case coaching.",
                "confidence": "medium",
            }
        ],
        competitor_assumptions=[
            {
                "topic": "General AI and education substitutes",
                "finding": "General AI assistants and study platforms may act as substitutes.",
                "rationale": "The brief names AI education and business coaching as the product context.",
                "confidence": "low",
            }
        ],
        unsupported_claims=[
            {
                "claim": "The AI education market is growing quickly.",
                "why_unsupported": "No external source or dated market report was provided.",
                "needed_evidence": ["Recent market research report", "Education technology adoption data"],
            }
        ],
        needs_human_review=["Confirm which MBA programs or student segments matter most."],
    )
    return analysis.model_dump_json()


class FakeResearchLLM:
    """Mock Research LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class FakeWebSearch:
    """Mock controlled search tool that records market and competitor queries."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def __call__(
        self,
        query: str,
        allowed_domains: list[str] | None,
        recency: str | None,
        max_results: int,
    ) -> list[WebSearchResult]:
        self.queries.append(query)
        return [
            WebSearchResult(
                title=f"Evidence for {query}",
                url=f"https://example.com/source-{len(self.queries)}",
                publisher="Example Research",
                published_date="2026-06-01",
                summary="A current source returned by the controlled search test double.",
                relevance_score=0.9,
                source_quality=SourceQuality.RESEARCH_ORG,
            )
        ]


class SequencedWebSearch:
    """Return or raise one configured outcome for each controlled query."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.queries: list[str] = []

    def __call__(
        self,
        query: str,
        allowed_domains: list[str] | None,
        recency: str | None,
        max_results: int,
    ) -> list[WebSearchResult]:
        self.queries.append(query)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome  # type: ignore[return-value]


def _web_result(identifier: str) -> WebSearchResult:
    """Build one valid result for partial-provider-failure tests."""
    return WebSearchResult(
        title=f"Evidence {identifier}",
        url=f"https://example.com/{identifier}",
        publisher="Example Research",
        published_date="2026-06-01",
        summary="A source that remains usable when the other query fails.",
        relevance_score=0.9,
        source_quality=SourceQuality.RESEARCH_ORG,
    )


class ResearchAgentTests(unittest.TestCase):
    """Tests for Research prompt construction and validated analysis output."""

    def test_build_research_prompt_includes_brief_and_output_boundaries(self) -> None:
        """The Research prompt contains user input and proposal-writing boundaries."""
        prompt = build_research_prompt(_complete_brief())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("market_trends", prompt)
        self.assertIn("customer_notes", prompt)
        self.assertIn("competitor_assumptions", prompt)
        self.assertIn("unsupported_claims", prompt)
        self.assertIn("Do not write a full business proposal", prompt)

    def test_research_agent_calls_mock_llm_and_returns_analysis(self) -> None:
        """The Research Agent parses fake LLM JSON into validated analysis."""
        events: list[AgentLogEvent] = []
        llm = FakeResearchLLM(_research_analysis_json())
        web_search = FakeWebSearch()
        agent = ResearchAgent(
            llm_client=llm,
            web_search_tool=web_search,
            log_hook=events.append,
        )

        analysis = agent.run(_complete_brief())

        self.assertIsInstance(analysis, ResearchAnalysis)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(analysis.market_trends[0].topic, "AI-assisted education workflows")
        self.assertEqual(analysis.competitor_assumptions[0].confidence, "low")
        self.assertEqual(len(analysis.unsupported_claims), 1)
        self.assertEqual([event.event_type for event in events], ["started", "completed"])
        self.assertEqual(len(web_search.queries), 2)
        self.assertIn("market trends research", web_search.queries[0])
        self.assertIn("competitors alternatives", web_search.queries[1])
        self.assertIn("Market Research Agent", llm.prompts[0])
        self.assertIn("Competitor Agent", llm.prompts[0])
        self.assertIn("https://example.com/source-1", llm.prompts[0])
        self.assertIn("https://example.com/source-2", llm.prompts[0])

    def test_research_analysis_rejects_full_proposal_fields(self) -> None:
        """Research output should not carry full proposal prose fields."""
        valid_payload = ResearchAnalysis.model_validate_json(_research_analysis_json()).model_dump()
        valid_payload["executive_summary"] = "This would be proposal writing, not research analysis."

        with self.assertRaises(ValidationError):
            ResearchAnalysis.model_validate(valid_payload)

    def test_provider_failure_keeps_results_from_the_other_query(self) -> None:
        """A failed market query does not discard competitor evidence."""
        web_search = SequencedWebSearch(
            [
                WebSearchRateLimitError("Tavily search rate limit reached."),
                [_web_result("competitor")],
            ]
        )
        agent = ResearchAgent(
            llm_client=FakeResearchLLM(_research_analysis_json()),
            web_search_tool=web_search,
        )

        with self.assertLogs("agents.research", level="WARNING"):
            sources = agent.collect_web_sources(_complete_brief())

        self.assertEqual(len(web_search.queries), 2)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].agent_name, "Competitor Agent")
        self.assertEqual(sources[0].url, "https://example.com/competitor")
        self.assertEqual(len(agent.web_search_warnings), 1)
        self.assertEqual(
            agent.web_search_warnings[0].error_type,
            "WebSearchRateLimitError",
        )

    def test_each_expected_external_failure_degrades_independently(self) -> None:
        """Configuration and timeout failures become two explicit warnings."""
        web_search = SequencedWebSearch(
            [
                WebSearchConfigurationError("TAVILY_API_KEY is not set."),
                requests.Timeout("Tavily request timed out."),
            ]
        )
        agent = ResearchAgent(
            llm_client=FakeResearchLLM(_research_analysis_json()),
            web_search_tool=web_search,
        )

        with self.assertLogs("agents.research", level="WARNING"):
            sources = agent.collect_web_sources(_complete_brief())

        self.assertEqual(sources, [])
        self.assertEqual(len(web_search.queries), 2)
        self.assertEqual(
            [warning.error_type for warning in agent.web_search_warnings],
            ["WebSearchConfigurationError", "Timeout"],
        )

    def test_provider_warning_is_given_to_research_llm(self) -> None:
        """The LLM is told not to invent evidence for the unavailable scope."""
        llm = FakeResearchLLM(_research_analysis_json())
        web_search = SequencedWebSearch(
            [
                WebSearchProviderError("Tavily service unavailable."),
                [_web_result("competitor")],
            ]
        )
        agent = ResearchAgent(llm_client=llm, web_search_tool=web_search)

        with self.assertLogs("agents.research", level="WARNING"):
            agent.run(_complete_brief())

        self.assertIn("Web Research Degradation Warnings", llm.prompts[0])
        self.assertIn("Tavily service unavailable.", llm.prompts[0])
        self.assertIn("Do not infer or invent the missing results", llm.prompts[0])

    def test_invalid_provider_result_schema_is_not_swallowed(self) -> None:
        """Malformed data is a contract bug, not an external-service fallback."""
        web_search = SequencedWebSearch(
            [
                [{"title": "", "url": "", "summary": ""}],
                [_web_result("unused")],
            ]
        )
        agent = ResearchAgent(
            llm_client=FakeResearchLLM(_research_analysis_json()),
            web_search_tool=web_search,
        )

        with self.assertRaises(ValidationError):
            agent.collect_web_sources(_complete_brief())

        self.assertEqual(len(web_search.queries), 1)
        self.assertEqual(agent.web_search_warnings, ())

    def test_programming_error_is_not_swallowed(self) -> None:
        """Unexpected code errors still fail fast for diagnosis."""
        web_search = SequencedWebSearch(
            [
                RuntimeError("test double bug"),
                [_web_result("unused")],
            ]
        )
        agent = ResearchAgent(
            llm_client=FakeResearchLLM(_research_analysis_json()),
            web_search_tool=web_search,
        )

        with self.assertRaisesRegex(RuntimeError, "test double bug"):
            agent.collect_web_sources(_complete_brief())

        self.assertEqual(len(web_search.queries), 1)


if __name__ == "__main__":
    unittest.main()
