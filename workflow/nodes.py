"""Deterministic workflow nodes for the proposal generation graph.

Phase 2 (Sprint 5) replaces the single monolithic prompt with discrete,
independently testable nodes. This module currently implements the
``InputValidator`` node (Sprint 5.2).

Per ``architecture_design.md`` (section 6.2), ``InputValidator`` takes the
``UserBrief`` and produces a ``MissingInfoReport`` *without* calling the LLM.
It only performs cheap, deterministic checks so the workflow can short-circuit
and ask the user to complete the form before any paid LLM call happens.
"""

from __future__ import annotations

from typing import Any

from workflow.state import WorkflowState

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
