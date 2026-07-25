"""Supervisor Agent for controlled multi-agent task planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from schemas.agent_outputs import SupervisorPlan
from workflow.llm_client import StructuredJsonLLM, create_default_llm_client

ROOT_DIR = Path(__file__).resolve().parent.parent
SUPERVISOR_PROMPT_PATH = ROOT_DIR / "prompts" / "supervisor.md"


class SupervisorLLM(Protocol):
    """Minimal LLM interface used by ``SupervisorAgent``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


def create_default_supervisor_llm() -> SupervisorLLM:
    """Create the default production LLM adapter for the Supervisor Agent."""
    return StructuredJsonLLM(
        create_default_llm_client(), SupervisorPlan, temperature=0.2
    )


def load_supervisor_prompt() -> str:
    """Load the Supervisor prompt template from disk."""
    if not SUPERVISOR_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Supervisor prompt not found: {SUPERVISOR_PROMPT_PATH}")
    return SUPERVISOR_PROMPT_PATH.read_text(encoding="utf-8")


def build_supervisor_prompt(user_brief: dict[str, Any]) -> str:
    """Build the complete prompt sent to the Supervisor LLM call.

    Args:
        user_brief: Validated user brief from the workflow or Streamlit form.

    Returns:
        Prompt text containing the Supervisor instructions plus serialized input.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2)

    return (
        f"{load_supervisor_prompt()}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```"
    )


def parse_supervisor_plan(raw_output: str) -> SupervisorPlan:
    """Parse and validate raw LLM JSON output as ``SupervisorPlan``.

    Args:
        raw_output: JSON string returned by the Supervisor LLM.

    Returns:
        A validated ``SupervisorPlan`` instance.

    Raises:
        ValueError: If the output is invalid JSON or fails schema validation.
    """
    try:
        return SupervisorPlan.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid SupervisorPlan output: {exc}") from exc


def build_supervisor_retry_prompt(
    original_prompt: str,
    validation_error: ValueError,
) -> str:
    """Request one corrected plan using the validation error as feedback."""
    return (
        f"{original_prompt}\n\n"
        "# Validation Correction\n\n"
        "Your previous SupervisorPlan failed schema validation:\n"
        f"{validation_error}\n\n"
        "Return the complete corrected JSON object only. Preserve required inputs "
        "by merging related input_requirements; do not silently truncate them."
    )


class SupervisorAgent(BaseAgent):
    """Agent that decomposes a validated brief into controlled downstream tasks."""

    def __init__(
        self,
        *,
        llm_client: SupervisorLLM | None = None,
        log_hook: AgentLogHook | None = None,
        prompt_path: str | Path = SUPERVISOR_PROMPT_PATH,
    ) -> None:
        """Create a Supervisor Agent with an optional injected LLM client."""
        super().__init__(
            name="Supervisor Agent",
            description="Splits proposal work and routes it to controlled worker agents.",
            prompt_path=prompt_path,
            log_hook=log_hook,
        )
        self._llm_client = llm_client

    def _run(self, input_data: Any) -> SupervisorPlan:
        """Return a validated task plan without producing analysis conclusions."""
        if not isinstance(input_data, dict):
            raise TypeError("SupervisorAgent input_data must be a user brief dictionary.")

        llm_client = self._llm_client or create_default_supervisor_llm()
        prompt = build_supervisor_prompt(input_data)
        raw_output = llm_client.generate_json(prompt)
        try:
            return parse_supervisor_plan(raw_output)
        except ValueError as exc:
            retry_prompt = build_supervisor_retry_prompt(prompt, exc)
            retry_output = llm_client.generate_json(retry_prompt)
            return parse_supervisor_plan(retry_output)
