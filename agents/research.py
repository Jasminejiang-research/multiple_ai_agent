"""Research Agent for controlled market, customer, and competitor analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import ResearchAnalysis
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
RESEARCH_PROMPT_PATH = ROOT_DIR / "prompts" / "research_agent.md"


class ResearchLLM(Protocol):
    """Minimal LLM interface used by ``ResearchAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


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


def build_research_prompt(user_brief: dict[str, Any]) -> str:
    """Build the complete prompt sent to the Research Agent LLM call.

    Args:
        user_brief: Validated user brief from the workflow or Streamlit form.

    Returns:
        Prompt text containing the Research Agent instructions plus serialized input.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2)

    return (
        f"{load_research_prompt()}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```"
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

    def _run(self, input_data: Any) -> ResearchAnalysis:
        """Return validated research analysis without proposal writing."""
        if not isinstance(input_data, dict):
            raise TypeError("ResearchAgent input_data must be a user brief dictionary.")

        llm_client = self._llm_client or create_default_research_llm()
        prompt = build_research_prompt(input_data)
        raw_output = llm_client.generate_json(prompt)
        return parse_research_analysis(raw_output)
