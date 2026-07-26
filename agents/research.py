"""Research Agent for controlled market, customer, and competitor analysis."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import requests
from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import ResearchAnalysis
from schemas.source import SourceRecord, WebSearchResult
from tools.tavily_search import WebSearchProviderError
from tools.web_search import search_web
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
RESEARCH_PROMPT_PATH = ROOT_DIR / "prompts" / "research_agent.md"
logger = logging.getLogger(__name__)


class ResearchLLM(Protocol):
    """Minimal LLM interface used by ``ResearchAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


WebSearchTool = Callable[
    [str, list[str] | None, str | None, int],
    list[WebSearchResult],
]


@dataclass(frozen=True, slots=True)
class WebResearchWarning:
    """One recoverable provider failure from a controlled research query."""

    agent_name: str
    query: str
    error_type: str
    message: str


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
    web_search_warnings: list[WebResearchWarning] | None = None,
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
    warnings_json = json.dumps(
        [asdict(warning) for warning in (web_search_warnings or [])],
        ensure_ascii=False,
        indent=2,
    )

    return (
        f"{load_research_prompt()}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```\n\n"
        "# Controlled Web Research Sources JSON\n\n"
        f"```json\n{sources_json}\n```\n\n"
        "# Web Research Degradation Warnings JSON\n\n"
        "Treat a failed search scope as unavailable evidence. Do not infer or "
        "invent the missing results.\n\n"
        f"```json\n{warnings_json}\n```"
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
        self._web_search_warnings: list[WebResearchWarning] = []

    @property
    def web_search_warnings(self) -> tuple[WebResearchWarning, ...]:
        """Return provider warnings from the most recent collection attempt."""
        return tuple(self._web_search_warnings)

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
        """Run approved searches independently and retain any partial evidence.

        Only expected external-provider failures are degraded. Invalid result
        schemas and programming errors deliberately remain visible to callers.
        """
        search_requests = (
            ("Market Research Agent", self._market_query(user_brief)),
            ("Competitor Agent", self._competitor_query(user_brief)),
        )
        sources: list[SourceRecord] = []
        self._web_search_warnings = []
        for agent_name, query in search_requests:
            try:
                results = self._web_search_tool(
                    query,
                    None,
                    "last_12_months",
                    5,
                )
            except (WebSearchProviderError, requests.Timeout, TimeoutError) as exc:
                warning = WebResearchWarning(
                    agent_name=agent_name,
                    query=query,
                    error_type=type(exc).__name__,
                    message=str(exc) or "Controlled web research failed.",
                )
                self._web_search_warnings.append(warning)
                logger.warning(
                    "Controlled web research degraded for %s: %s",
                    agent_name,
                    warning.message,
                    extra={
                        "web_research_agent": agent_name,
                        "web_search_query": query,
                        "web_search_error_type": warning.error_type,
                    },
                )
                continue

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
        prompt = build_research_prompt(
            prompt_brief,
            web_sources,
            list(self.web_search_warnings),
        )
        raw_output = llm_client.generate_json(prompt)
        return parse_research_analysis(raw_output)
