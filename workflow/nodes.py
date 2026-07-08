"""Deterministic workflow nodes for the proposal generation graph.

Phase 2 (Sprint 5) replaces the single monolithic prompt with discrete,
independently testable nodes. This module currently implements the
``InputValidator`` node (Sprint 5.2) and ``ProposalPlanner`` node (Sprint 5.3).

Per ``architecture_design.md`` (section 6.2), ``InputValidator`` takes the
``UserBrief`` and produces a ``MissingInfoReport`` *without* calling the LLM.
It only performs cheap, deterministic checks so the workflow can short-circuit
and ask the user to complete the form before any paid LLM call happens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from typing import Any

from pydantic import ValidationError

from schemas.workflow import PROPOSAL_SECTION_TITLES, ProposalOutline
from workflow.state import WorkflowState

ROOT_DIR = Path(__file__).resolve().parent.parent
PLANNER_PROMPT_PATH = ROOT_DIR / "prompts" / "planner.md"


class PlannerLLM(Protocol):
    """Minimal LLM interface used by ``proposal_planner_node``.

    Implementations receive a complete planner prompt and return JSON text
    matching ``ProposalOutline``. Tests can provide a small fake object.
    """

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""

# Required brief fields, mirroring the ``UserBrief`` schema in
# architecture_design.md (section 8.2). ``stage``, ``known_competitors`` and
# ``additional_context`` are intentionally optional and not validated here.
REQUIRED_BRIEF_FIELDS: tuple[str, ...] = (
    "company_or_product_name",
    "industry",
    "target_customer",
    "problem",
    "solution",
    "business_model",
    "geography",
    "proposal_goal",
)

# Per-field minimum character length (after trimming surrounding whitespace).
# Descriptive fields demand more substance than short label-like fields so the
# downstream planner has enough signal to work with.
MIN_FIELD_LENGTHS: dict[str, int] = {
    "company_or_product_name": 2,
    "industry": 2,
    "target_customer": 3,
    "problem": 10,
    "solution": 10,
    "business_model": 3,
    "geography": 2,
    "proposal_goal": 3,
}


def validate_user_brief(user_brief: dict[str, Any]) -> list[str]:
    """Validate a raw user brief and return a list of human-readable issues.

    Args:
        user_brief: Mapping of brief field names to user-supplied values.

    Returns:
        A list of issue messages. An empty list means the brief is complete
        and every field meets its minimum length requirement. No LLM is called.
    """
    issues: list[str] = []

    for field in REQUIRED_BRIEF_FIELDS:
        raw_value = user_brief.get(field)
        value = str(raw_value).strip() if raw_value is not None else ""

        if not value:
            issues.append(f"Missing required field: {field}")
            continue

        min_length = MIN_FIELD_LENGTHS.get(field, 1)
        if len(value) < min_length:
            issues.append(
                f"Field '{field}' is too short (minimum {min_length} characters)"
            )

    return issues


def input_validator_node(state: WorkflowState) -> WorkflowState:
    """Deterministically validate the user brief held in the workflow state.

    Reads ``state['user_brief']``, checks for missing required fields and
    fields that are too short, and writes the resulting issue list to
    ``missing_info``. This node never calls the LLM.

    Args:
        state: Current workflow state. Expected to contain ``user_brief``.

    Returns:
        A partial state update with ``missing_info`` and ``current_step``,
        following the LangGraph convention of returning only changed keys.
    """
    user_brief = state.get("user_brief") or {}
    missing_info = validate_user_brief(user_brief)

    return {
        "missing_info": missing_info,
        "current_step": "input_validator",
    }


def load_planner_prompt() -> str:
    """Load the ProposalPlanner prompt template from disk."""
    if not PLANNER_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Planner prompt not found: {PLANNER_PROMPT_PATH}")
    return PLANNER_PROMPT_PATH.read_text(encoding="utf-8")


def build_planner_prompt(user_brief: dict[str, Any]) -> str:
    """Build the complete prompt sent to the ProposalPlanner LLM call.

    Args:
        user_brief: Validated user brief from the workflow state.

    Returns:
        Prompt text containing the planner instructions, required section
        titles, and the current brief serialized as JSON.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2)
    section_titles = "\n".join(f"- {title}" for title in PROPOSAL_SECTION_TITLES)

    return (
        f"{load_planner_prompt()}\n\n"
        "# Required Section Titles\n\n"
        f"{section_titles}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```"
    )


def parse_proposal_outline(raw_output: str) -> ProposalOutline:
    """Parse and validate the raw LLM JSON output as ``ProposalOutline``.

    Args:
        raw_output: JSON string returned by the planner LLM.

    Returns:
        A validated ``ProposalOutline`` instance.

    Raises:
        ValueError: If the output is not valid JSON or fails Pydantic validation.
    """
    try:
        return ProposalOutline.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid ProposalOutline output: {exc}") from exc


def proposal_planner_node(
    state: WorkflowState,
    llm_client: PlannerLLM | None = None,
) -> WorkflowState:
    """Call the LLM planner and save a validated proposal outline to state.

    Args:
        state: Current workflow state. Expected to contain ``user_brief``.
        llm_client: Optional test or production LLM adapter implementing
            ``generate_json(prompt: str) -> str``.

    Returns:
        A partial state update with ``proposal_outline`` and ``current_step``.
    """
    if llm_client is None:
        from workflow.llm import create_default_planner_llm

        llm_client = create_default_planner_llm()

    user_brief = state.get("user_brief") or {}
    prompt = build_planner_prompt(user_brief)
    raw_output = llm_client.generate_json(prompt)
    proposal_outline = parse_proposal_outline(raw_output)

    return {
        "proposal_outline": proposal_outline.model_dump(),
        "current_step": "proposal_planner",
    }
