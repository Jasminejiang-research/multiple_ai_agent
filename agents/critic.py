"""Critic Agent for structured review of proposal drafts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.workflow import CritiqueReport, ProposalDraft
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
CRITIC_PROMPT_PATH = ROOT_DIR / "prompts" / "critic_agent.md"


class CriticLLM(Protocol):
    """Minimal LLM interface used by ``CriticAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


def create_default_critic_llm() -> CriticLLM:
    """Create the default production LLM adapter for the Critic Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), CritiqueReport, temperature=0.2
    )


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
