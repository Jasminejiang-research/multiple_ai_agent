"""Research Agent for controlled market, customer, and competitor analysis."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import ResearchAnalysis
from workflow.gemini_schema import relaxed_response_schema

ROOT_DIR = Path(__file__).resolve().parent.parent
RESEARCH_PROMPT_PATH = ROOT_DIR / "prompts" / "research_agent.md"
MODEL_NAME = "gemini-2.5-flash"

_RESEARCH_SCHEMA = relaxed_response_schema(ResearchAnalysis)


class ResearchLLM(Protocol):
    """Minimal LLM interface used by ``ResearchAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class GeminiResearchLLM:
    """Gemini-backed JSON generator for the Research Agent."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``ResearchAnalysis`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESEARCH_SCHEMA,
                temperature=0.2,
            ),
        )

        if not response.text:
            raise ValueError("Gemini returned an empty research response.")

        return ResearchAnalysis.model_validate_json(response.text).model_dump_json()


def create_default_research_llm() -> GeminiResearchLLM:
    """Create the default production LLM adapter for the Research Agent."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiResearchLLM(api_key=api_key, model_name=model_name)


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
