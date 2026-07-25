"""Research Agent for controlled market, customer, and competitor analysis."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import ResearchAnalysis
from schemas.source import SourceRecord, WebSearchResult
from tools.web_search import search_web
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
RESEARCH_PROMPT_PATH = ROOT_DIR / "prompts" / "research_agent.md"


class ResearchLLM(Protocol):
    """Minimal LLM interface used by ``ResearchAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


WebSearchTool = Callable[
    [str, list[str] | None, str | None, int],
    list[WebSearchResult],
]


def create_default_research_llm() -> ResearchLLM:
    """Create the default production LLM adapter for the Research Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), ResearchAnalysis, temperature=0.2
    )


def load_research_prompt() -> str:
    """Load the Research Agent prompt template from disk."""
    if not RESEARCH_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Research Agent prompt not found: {RESEARCH_PROMPT_PATH}")
    return RESEARCH_PROMPT_PATH.read_text(encoding="utf-8")


def build_research_prompt(
    user_brief: dict[str, Any],
    web_sources: list[SourceRecord] | None = None,
) -> str:
    """Build the complete prompt sent to the Research Agent LLM call.

    Args:
        user_brief: Validated user brief from the workflow or Streamlit form.

    Returns:
        Prompt text containing the Research Agent instructions plus serialized input.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2, default=str)
    sources_json = json.dumps(
        [
            source.model_dump(mode="json")
            for source in (web_sources or [])
        ],
        ensure_ascii=False,
        indent=2,
    )

    return (
        f"{load_research_prompt()}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```\n\n"
        "# Controlled Web Research Sources JSON\n\n"
        f"```json\n{sources_json}\n```"
    )


def parse_research_analysis(raw_output: str) -> ResearchAnalysis:
    """Parse and validate raw LLM JSON output as ``ResearchAnalysis``.

    Args:
        raw_output: JSON string returned by the Research Agent LLM.

    Returns:
        A validated ``ResearchAnalysis`` instance.

    Raises:
        ValueError: If the output is invalid JSON or fails schema validation.
    """
    try:
        return ResearchAnalysis.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid ResearchAnalysis output: {exc}") from exc


class ResearchAgent(BaseAgent):
    """Agent that produces research hypotheses without writing a full proposal."""

    def __init__(
        self,
        *,
        llm_client: ResearchLLM | None = None,
        web_search_tool: WebSearchTool = search_web,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = RESEARCH_PROMPT_PATH,
    ) -> None:
        """Create a Research Agent with an optional injected LLM client."""
        super().__init__(
            name="Research Agent",
            description="Analyzes market, customer, and competitor assumptions from a validated brief.",
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client
        self._web_search_tool = web_search_tool

    @staticmethod
    def _market_query(user_brief: dict[str, Any]) -> str:
        """Build the controlled market-research query from validated brief fields."""
        return " ".join(
            str(value).strip()
            for value in (
                user_brief.get("industry"),
                user_brief.get("geography"),
                user_brief.get("target_customer"),
                "market trends research",
            )
            if value
        )

    @staticmethod
    def _competitor_query(user_brief: dict[str, Any]) -> str:
        """Build the controlled competitor query from validated brief fields."""
        known_competitors = user_brief.get("known_competitors")
        if isinstance(known_competitors, list):
            known_competitors = " ".join(str(item) for item in known_competitors)
        return " ".join(
            str(value).strip()
            for value in (
                user_brief.get("industry"),
                user_brief.get("solution"),
                user_brief.get("target_customer"),
                user_brief.get("geography"),
                known_competitors,
                "competitors alternatives",
            )
            if value
        )

    def collect_web_sources(
        self,
        user_brief: dict[str, Any],
    ) -> list[SourceRecord]:
        """Run only the approved market and competitor web-search scopes."""
        search_requests = (
            ("Market Research Agent", self._market_query(user_brief)),
            ("Competitor Agent", self._competitor_query(user_brief)),
        )
        sources: list[SourceRecord] = []
        for agent_name, query in search_requests:
            results = self._web_search_tool(query, None, "last_12_months", 5)
            retrieved_at = datetime.now(timezone.utc)
            for result in results:
                normalized_result = WebSearchResult.model_validate(result)
                sources.append(
                    SourceRecord(
                        source_id=f"web-{uuid4().hex}",
                        agent_name=agent_name,
                        query=query,
                        retrieved_at=retrieved_at,
                        **normalized_result.model_dump(),
                    )
                )
        return sources

    def _run(self, input_data: Any) -> ResearchAnalysis:
        """Return web-grounded research analysis without proposal writing."""
        if not isinstance(input_data, dict):
            raise TypeError("ResearchAgent input_data must be a user brief dictionary.")

        raw_sources = input_data.get("web_research_sources")
        if raw_sources is None:
            web_sources = self.collect_web_sources(input_data)
        else:
            if not isinstance(raw_sources, list):
                raise TypeError("web_research_sources must be a list.")
            web_sources = [
                SourceRecord.model_validate(source) for source in raw_sources
            ]

        prompt_brief = {
            key: value
            for key, value in input_data.items()
            if key != "web_research_sources"
        }
        llm_client = self._llm_client or create_default_research_llm()
        prompt = build_research_prompt(prompt_brief, web_sources)
        raw_output = llm_client.generate_json(prompt)
        return parse_research_analysis(raw_output)
