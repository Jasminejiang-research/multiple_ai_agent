"""Writer Agent for assembling validated analysis into a proposal draft."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import WriterInput
from schemas.workflow import PROPOSAL_SECTION_FIELD_NAMES, ProposalDraft
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
WRITER_PROMPT_PATH = ROOT_DIR / "prompts" / "writer_agent.md"


class WriterLLM(Protocol):
    """Minimal LLM interface used by ``WriterAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


def create_default_writer_llm() -> WriterLLM:
    """Create the default production LLM adapter for the Writer Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), ProposalDraft, temperature=0.2
    )


def load_writer_prompt() -> str:
    """Load the Writer Agent prompt template from disk."""
    if not WRITER_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Writer Agent prompt not found: {WRITER_PROMPT_PATH}")
    return WRITER_PROMPT_PATH.read_text(encoding="utf-8")


def build_writer_prompt(input_data: dict[str, Any] | WriterInput) -> str:
    """Build a Writer prompt from validated research, strategy, and finance packets.

    Args:
        input_data: Structured analysis packets and filtered RAG evidence.

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


def validate_proposal_source_ids(
    proposal: ProposalDraft,
    writer_input: WriterInput,
) -> None:
    """Reject source IDs that do not exist in the supplied RAG evidence."""
    allowed_source_ids = {
        chunk.source_id for chunk in writer_input.evidence_chunks
    }
    for field_name in PROPOSAL_SECTION_FIELD_NAMES:
        section = getattr(proposal, field_name)
        unknown_source_ids = sorted(set(section.source_ids) - allowed_source_ids)
        if unknown_source_ids:
            raise ValueError(
                f"ProposalDraft.{field_name} cites unknown source IDs: "
                + ", ".join(unknown_source_ids)
            )


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
        """Return an evidence-grounded, validated 13-section proposal."""
        if not isinstance(input_data, (dict, WriterInput)):
            raise TypeError("WriterAgent input_data must be a dictionary or WriterInput.")

        try:
            writer_input = (
                input_data
                if isinstance(input_data, WriterInput)
                else WriterInput.model_validate(input_data)
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid WriterInput: {exc}") from exc

        prompt = build_writer_prompt(writer_input)
        llm_client = self._llm_client or create_default_writer_llm()
        raw_output = llm_client.generate_json(prompt)
        proposal = parse_proposal_draft(raw_output)
        validate_proposal_source_ids(proposal, writer_input)
        return proposal
