"""Critic Agent for structured review of proposal drafts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.workflow import CritiqueReport, ProposalDraft
from workflow.gemini_schema import relaxed_response_schema

ROOT_DIR = Path(__file__).resolve().parent.parent
CRITIC_PROMPT_PATH = ROOT_DIR / "prompts" / "critic_agent.md"
MODEL_NAME = "gemini-2.5-flash"

_CRITIQUE_SCHEMA = relaxed_response_schema(CritiqueReport)


class CriticLLM(Protocol):
    """Minimal LLM interface used by ``CriticAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class GeminiCriticLLM:
    """Gemini-backed JSON generator for the Critic Agent."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``CritiqueReport`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_CRITIQUE_SCHEMA,
                temperature=0.2,
            ),
        )

        if not response.text:
            raise ValueError("Gemini returned an empty critic response.")

        return CritiqueReport.model_validate_json(response.text).model_dump_json()


def create_default_critic_llm() -> GeminiCriticLLM:
    """Create the default production LLM adapter for the Critic Agent."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiCriticLLM(api_key=api_key, model_name=model_name)


def load_critic_prompt() -> str:
    """Load the Critic Agent prompt template from disk."""
    if not CRITIC_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Critic Agent prompt not found: {CRITIC_PROMPT_PATH}")
    return CRITIC_PROMPT_PATH.read_text(encoding="utf-8")


def build_critic_prompt(input_data: dict[str, Any] | ProposalDraft) -> str:
    """Build a Critic prompt from one strictly validated proposal draft.

    Args:
        input_data: The complete proposal draft to review.

    Returns:
        Critic instructions followed by the serialized validated draft.
    """
    try:
        proposal_draft = (
            input_data
            if isinstance(input_data, ProposalDraft)
            else ProposalDraft.model_validate(input_data)
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid ProposalDraft: {exc}") from exc

    return (
        f"{load_critic_prompt()}\n\n"
        "# ProposalDraft Input JSON\n\n"
        f"```json\n{proposal_draft.model_dump_json(indent=2)}\n```"
    )


def parse_critique_report(raw_output: str) -> CritiqueReport:
    """Parse and strictly validate raw Critic JSON as ``CritiqueReport``."""
    try:
        return CritiqueReport.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid CritiqueReport output: {exc}") from exc


class CriticAgent(BaseAgent):
    """Agent that identifies proposal issues without rewriting the draft."""

    def __init__(
        self,
        *,
        llm_client: CriticLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = CRITIC_PROMPT_PATH,
    ) -> None:
        """Create a Critic Agent with an optional injected LLM client."""
        super().__init__(
            name="Critic Agent",
            description=(
                "Reviews unsupported claims, financial consistency, and GTM quality."
            ),
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> CritiqueReport:
        """Return a validated critique and leave the proposal unchanged."""
        if not isinstance(input_data, (dict, ProposalDraft)):
            raise TypeError("CriticAgent input_data must be a dictionary or ProposalDraft.")

        prompt = build_critic_prompt(input_data)
        llm_client = self._llm_client or create_default_critic_llm()
        raw_output = llm_client.generate_json(prompt)
        return parse_critique_report(raw_output)
