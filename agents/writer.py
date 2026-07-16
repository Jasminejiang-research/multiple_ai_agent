"""Writer Agent for assembling validated analysis into a proposal draft."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import WriterInput
from schemas.workflow import ProposalDraft
from workflow.gemini_schema import relaxed_response_schema

ROOT_DIR = Path(__file__).resolve().parent.parent
WRITER_PROMPT_PATH = ROOT_DIR / "prompts" / "writer_agent.md"
MODEL_NAME = "gemini-2.5-flash"

_WRITER_SCHEMA = relaxed_response_schema(ProposalDraft)


class WriterLLM(Protocol):
    """Minimal LLM interface used by ``WriterAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class GeminiWriterLLM:
    """Gemini-backed JSON generator for the Writer Agent."""

    def __init__(self, api_key: str, model_name: str = MODEL_NAME) -> None:
        """Initialize the Gemini client with an API key and model name."""
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    def generate_json(self, prompt: str) -> str:
        """Return JSON text matching the ``ProposalDraft`` schema."""
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_WRITER_SCHEMA,
                temperature=0.2,
            ),
        )

        if not response.text:
            raise ValueError("Gemini returned an empty writer response.")

        return ProposalDraft.model_validate_json(response.text).model_dump_json()


def create_default_writer_llm() -> GeminiWriterLLM:
    """Create the default production LLM adapter for the Writer Agent."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")
    model_name = os.getenv("DEFAULT_MODEL", MODEL_NAME)
    return GeminiWriterLLM(api_key=api_key, model_name=model_name)


def load_writer_prompt() -> str:
    """Load the Writer Agent prompt template from disk."""
    if not WRITER_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Writer Agent prompt not found: {WRITER_PROMPT_PATH}")
    return WRITER_PROMPT_PATH.read_text(encoding="utf-8")


def build_writer_prompt(input_data: dict[str, Any] | WriterInput) -> str:
    """Build a Writer prompt from validated research, strategy, and finance packets.

    Args:
        input_data: The three structured analysis packets required by the Writer.

    Returns:
        Prompt text containing Writer instructions and serialized validated input.
    """
    try:
        writer_input = (
            input_data
            if isinstance(input_data, WriterInput)
            else WriterInput.model_validate(input_data)
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid WriterInput: {exc}") from exc

    return (
        f"{load_writer_prompt()}\n\n"
        "# Writer Input JSON\n\n"
        f"```json\n{writer_input.model_dump_json(indent=2)}\n```"
    )


def parse_proposal_draft(raw_output: str) -> ProposalDraft:
    """Parse and strictly validate raw Writer JSON as ``ProposalDraft``."""
    try:
        return ProposalDraft.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid ProposalDraft output: {exc}") from exc


class WriterAgent(BaseAgent):
    """Agent that writes a proposal using only supplied analysis packets."""

    def __init__(
        self,
        *,
        llm_client: WriterLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = WRITER_PROMPT_PATH,
    ) -> None:
        """Create a Writer Agent with an optional injected LLM client."""
        super().__init__(
            name="Writer Agent",
            description="Combines validated research, strategy, and finance into a proposal draft.",
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> ProposalDraft:
        """Return a validated 13-section proposal without introducing new facts."""
        if not isinstance(input_data, (dict, WriterInput)):
            raise TypeError("WriterAgent input_data must be a dictionary or WriterInput.")

        prompt = build_writer_prompt(input_data)
        llm_client = self._llm_client or create_default_writer_llm()
        raw_output = llm_client.generate_json(prompt)
        return parse_proposal_draft(raw_output)
