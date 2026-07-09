"""Strategy Agent for controlled positioning, business model, and GTM analysis."""

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
from schemas.agent_outputs import StrategyAnalysis
from workflow.gemini_schema import relaxed_response_schema

ROOT_DIR = Path(__file__).resolve().parent.parent
STRATEGY_PROMPT_PATH = ROOT_DIR / "prompts" / "strategy_agent.md"
MODEL_NAME = "gemini-2.5-flash"

_STRATEGY_SCHEMA = relaxed_response_schema(StrategyAnalysis)


class StrategyLLM(Protocol):
    """Minimal LLM interface used by ``StrategyAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class GeminiStrategyLLM:
    """Gemini-backed JSON generator for the Strategy Agent."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``StrategyAnalysis`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_STRATEGY_SCHEMA,
                temperature=0.2,
            ),
        )

        if not response.text:
            raise ValueError("Gemini returned an empty strategy response.")

        return StrategyAnalysis.model_validate_json(response.text).model_dump_json()


def create_default_strategy_llm() -> GeminiStrategyLLM:
    """Create the default production LLM adapter for the Strategy Agent."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiStrategyLLM(api_key=api_key, model_name=model_name)


def load_strategy_prompt() -> str:
    """Load the Strategy Agent prompt template from disk."""
    if not STRATEGY_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Strategy Agent prompt not found: {STRATEGY_PROMPT_PATH}")
    return STRATEGY_PROMPT_PATH.read_text(encoding="utf-8")


def build_strategy_prompt(input_data: dict[str, Any]) -> str:
    """Build the complete prompt sent to the Strategy Agent LLM call.

    Args:
        input_data: Structured brief and optional prior analysis packets.

    Returns:
        Prompt text containing the Strategy Agent instructions plus serialized input.
    """
    input_json = json.dumps(input_data, ensure_ascii=False, indent=2)

    return (
        f"{load_strategy_prompt()}\n\n"
        "# Strategy Input JSON\n\n"
        f"```json\n{input_json}\n```"
    )


def parse_strategy_analysis(raw_output: str) -> StrategyAnalysis:
    """Parse and validate raw LLM JSON output as ``StrategyAnalysis``.

    Args:
        raw_output: JSON string returned by the Strategy Agent LLM.

    Returns:
        A validated ``StrategyAnalysis`` instance.

    Raises:
        ValueError: If the output is invalid JSON or fails schema validation.
    """
    try:
        return StrategyAnalysis.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid StrategyAnalysis output: {exc}") from exc


class StrategyAgent(BaseAgent):
    """Agent that produces strategic analysis without inventing market data."""

    def __init__(
        self,
        *,
        llm_client: StrategyLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = STRATEGY_PROMPT_PATH,
    ) -> None:
        """Create a Strategy Agent with an optional injected LLM client."""
        super().__init__(
            name="Strategy Agent",
            description="Designs value proposition, business model logic, GTM, and moat hypotheses.",
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> StrategyAnalysis:
        """Return validated strategy analysis without proposal writing."""
        if not isinstance(input_data, dict):
            raise TypeError("StrategyAgent input_data must be a dictionary.")

        llm_client = self._llm_client or create_default_strategy_llm()
        prompt = build_strategy_prompt(input_data)
        raw_output = llm_client.generate_json(prompt)
        return parse_strategy_analysis(raw_output)
