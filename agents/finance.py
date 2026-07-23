"""Finance Agent for controlled financial assumption analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import FinanceAssumptions
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
FINANCE_PROMPT_PATH = ROOT_DIR / "prompts" / "finance_agent.md"


class FinanceLLM(Protocol):
    """Minimal LLM interface used by ``FinanceAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


def create_default_finance_llm() -> FinanceLLM:
    """Create the default production LLM adapter for the Finance Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), FinanceAssumptions, temperature=0.2
    )


def load_finance_prompt() -> str:
    """Load the Finance Agent prompt template from disk."""
    if not FINANCE_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Finance Agent prompt not found: {FINANCE_PROMPT_PATH}")
    return FINANCE_PROMPT_PATH.read_text(encoding="utf-8")


def build_finance_prompt(input_data: dict[str, Any]) -> str:
    """Build the complete prompt sent to the Finance Agent LLM call.

    Args:
        input_data: Structured brief and optional research or strategy packets.

    Returns:
        Prompt text containing the Finance Agent instructions plus serialized input.
    """
    input_json = json.dumps(input_data, ensure_ascii=False, indent=2)

    return (
        f"{load_finance_prompt()}\n\n"
        "# Finance Input JSON\n\n"
        f"```json\n{input_json}\n```"
    )


def parse_finance_assumptions(raw_output: str) -> FinanceAssumptions:
    """Parse and validate raw LLM JSON output as ``FinanceAssumptions``.

    Args:
        raw_output: JSON string returned by the Finance Agent LLM.

    Returns:
        A validated ``FinanceAssumptions`` instance.

    Raises:
        ValueError: If the output is invalid JSON or fails schema validation.
    """
    try:
        return FinanceAssumptions.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid FinanceAssumptions output: {exc}") from exc


class FinanceAgent(BaseAgent):
    """Agent that produces financial assumptions without claiming forecast accuracy."""

    def __init__(
        self,
        *,
        llm_client: FinanceLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = FINANCE_PROMPT_PATH,
    ) -> None:
        """Create a Finance Agent with an optional injected LLM client."""
        super().__init__(
            name="Finance Agent",
            description="Frames revenue, cost, unit economics, and break-even assumptions.",
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> FinanceAssumptions:
        """Return validated finance assumptions without proposal writing."""
        if not isinstance(input_data, dict):
            raise TypeError("FinanceAgent input_data must be a dictionary.")

        llm_client = self._llm_client or create_default_finance_llm()
        prompt = build_finance_prompt(input_data)
        raw_output = llm_client.generate_json(prompt)
        return parse_finance_assumptions(raw_output)
