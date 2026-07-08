"""Deterministic workflow nodes for the proposal generation graph.

Phase 2 (Sprint 5) replaces the single monolithic prompt with discrete,
independently testable nodes. This module currently implements the
``InputValidator`` node (Sprint 5.2), ``ProposalPlanner`` node (Sprint 5.3),
``SectionWriter`` node (Sprint 5.4), and ``ProposalAssembler`` node
(Sprint 5.5).

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

from schemas.workflow import (
    PROPOSAL_SECTION_TITLES,
    SECTION_FIELD_BY_TITLE,
    CritiqueReport,
    ProposalDraft,
    ProposalOutline,
    ProposalSection,
    SectionDrafts,
)
from workflow.state import WorkflowState

ROOT_DIR = Path(__file__).resolve().parent.parent
PLANNER_PROMPT_PATH = ROOT_DIR / "prompts" / "planner.md"
SECTION_WRITER_PROMPT_PATH = ROOT_DIR / "prompts" / "section_writer.md"
BASIC_CRITIC_PROMPT_PATH = ROOT_DIR / "prompts" / "basic_critic.md"


class PlannerLLM(Protocol):
    """Minimal LLM interface used by ``proposal_planner_node``.

    Implementations receive a complete planner prompt and return JSON text
    matching ``ProposalOutline``. Tests can provide a small fake object.
    """

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class SectionWriterLLM(Protocol):
    """Minimal LLM interface used by ``section_writer_node``."""

    def generate_json(self, prompt: str) -> str:
        """Generate a JSON response for the provided prompt."""


class BasicCriticLLM(Protocol):
    """Minimal LLM interface used by ``basic_critic_node``."""

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


def load_section_writer_prompt() -> str:
    """Load the SectionWriter prompt template from disk."""
    if not SECTION_WRITER_PROMPT_PATH.is_file():
        raise FileNotFoundError(
            f"SectionWriter prompt not found: {SECTION_WRITER_PROMPT_PATH}"
        )
    return SECTION_WRITER_PROMPT_PATH.read_text(encoding="utf-8")


def build_section_writer_prompt(
    user_brief: dict[str, Any],
    proposal_outline: dict[str, Any],
) -> str:
    """Build the complete prompt sent to the SectionWriter LLM call.

    Args:
        user_brief: Validated user brief from the workflow state.
        proposal_outline: Planner output already validated as ``ProposalOutline``.

    Returns:
        Prompt text containing writer instructions plus serialized inputs.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2)
    outline_json = json.dumps(proposal_outline, ensure_ascii=False, indent=2)
    section_titles = "\n".join(f"- {title}" for title in PROPOSAL_SECTION_TITLES)

    return (
        f"{load_section_writer_prompt()}\n\n"
        "# Required Section Titles\n\n"
        f"{section_titles}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```\n\n"
        "# Proposal Outline JSON\n\n"
        f"```json\n{outline_json}\n```"
    )


def parse_section_drafts(raw_output: str) -> SectionDrafts:
    """Parse and validate the raw LLM JSON output as ``SectionDrafts``.

    Args:
        raw_output: JSON string returned by the SectionWriter LLM.

    Returns:
        A validated ``SectionDrafts`` instance.

    Raises:
        ValueError: If the output is not valid JSON or fails Pydantic validation.
    """
    try:
        return SectionDrafts.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid SectionDrafts output: {exc}") from exc


def section_writer_node(
    state: WorkflowState,
    llm_client: SectionWriterLLM | None = None,
) -> WorkflowState:
    """Call the LLM writer and save validated section drafts to state.

    This node writes the 13 fixed proposal sections from the planner outline.
    It does not critique, revise, assemble, or call any tools.

    Args:
        state: Current workflow state. Expected to contain ``user_brief`` and
            ``proposal_outline``.
        llm_client: Optional test or production LLM adapter implementing
            ``generate_json(prompt: str) -> str``.

    Returns:
        A partial state update with ``section_drafts`` and ``current_step``.
    """
    if llm_client is None:
        from workflow.llm import create_default_section_writer_llm

        llm_client = create_default_section_writer_llm()

    user_brief = state.get("user_brief") or {}
    proposal_outline = state.get("proposal_outline")
    if proposal_outline is None:
        raise ValueError("section_writer_node requires proposal_outline in state.")

    prompt = build_section_writer_prompt(user_brief, proposal_outline)
    raw_output = llm_client.generate_json(prompt)
    section_drafts = parse_section_drafts(raw_output)

    return {
        "section_drafts": section_drafts.model_dump(),
        "current_step": "section_writer",
    }


def assemble_proposal_draft(section_drafts: dict[str, Any] | SectionDrafts) -> ProposalDraft:
    """Assemble validated section drafts into a full ``ProposalDraft``.

    Args:
        section_drafts: Raw state dictionary or already validated
            ``SectionDrafts`` object from the SectionWriter node.

    Returns:
        A validated ``ProposalDraft`` with one field per required section.

    Raises:
        ValueError: If drafts are missing, invalid, duplicated, or out of order.
    """
    try:
        drafts = (
            section_drafts
            if isinstance(section_drafts, SectionDrafts)
            else SectionDrafts.model_validate(section_drafts)
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid SectionDrafts input: {exc}") from exc

    proposal_data: dict[str, Any] = {"title": drafts.proposal_title}
    for section in drafts.sections:
        field_name = SECTION_FIELD_BY_TITLE[section.title]
        proposal_data[field_name] = ProposalSection.model_validate(section.model_dump())

    try:
        return ProposalDraft.model_validate(proposal_data)
    except ValidationError as exc:
        raise ValueError(f"Invalid assembled ProposalDraft: {exc}") from exc


def render_proposal_preview(proposal_draft: ProposalDraft) -> str:
    """Render an assembled proposal draft as a deterministic Markdown preview.

    Args:
        proposal_draft: Validated full proposal draft from the assembler.

    Returns:
        Markdown text with the title, all 13 sections, confidence, key claims,
        and source IDs for quick review before critique or export.
    """
    lines: list[str] = [f"# {proposal_draft.title}", ""]

    for section_title in PROPOSAL_SECTION_TITLES:
        field_name = SECTION_FIELD_BY_TITLE[section_title]
        section = getattr(proposal_draft, field_name)
        lines.extend(
            [
                f"## {section.title}",
                "",
                f"**Confidence:** {section.confidence}",
                "",
                section.content,
                "",
            ]
        )

        if section.key_claims:
            lines.extend(["**Key Claims:**", ""])
            lines.extend(f"- {claim}" for claim in section.key_claims)
            lines.append("")

        if section.source_ids:
            lines.extend(["**Source IDs:**", ""])
            lines.extend(f"- {source_id}" for source_id in section.source_ids)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def proposal_assembler_node(state: WorkflowState) -> WorkflowState:
    """Combine SectionWriter output into a full proposal and Markdown preview.

    This node is deterministic: it validates the existing 13 section drafts,
    maps them to the fixed ``ProposalDraft`` fields, renders a preview, and
    never calls the LLM.

    Args:
        state: Current workflow state. Expected to contain ``section_drafts``.

    Returns:
        A partial state update with ``proposal_draft``, ``markdown_preview``,
        and ``current_step``.
    """
    section_drafts = state.get("section_drafts")
    if section_drafts is None:
        raise ValueError("proposal_assembler_node requires section_drafts in state.")

    proposal_draft = assemble_proposal_draft(section_drafts)
    markdown_preview = render_proposal_preview(proposal_draft)

    return {
        "proposal_draft": proposal_draft.model_dump(),
        "markdown_preview": markdown_preview,
        "current_step": "proposal_assembler",
    }


def load_basic_critic_prompt() -> str:
    """Load the BasicCritic prompt template from disk."""
    if not BASIC_CRITIC_PROMPT_PATH.is_file():
        raise FileNotFoundError(
            f"BasicCritic prompt not found: {BASIC_CRITIC_PROMPT_PATH}"
        )
    return BASIC_CRITIC_PROMPT_PATH.read_text(encoding="utf-8")


def build_basic_critic_prompt(
    user_brief: dict[str, Any],
    proposal_draft: dict[str, Any],
) -> str:
    """Build the complete prompt sent to the BasicCritic LLM call.

    Args:
        user_brief: Validated user brief from the workflow state.
        proposal_draft: Assembled draft already validated as ``ProposalDraft``.

    Returns:
        Prompt text containing critic instructions plus serialized inputs.
    """
    brief_json = json.dumps(user_brief, ensure_ascii=False, indent=2)
    draft_json = json.dumps(proposal_draft, ensure_ascii=False, indent=2)

    return (
        f"{load_basic_critic_prompt()}\n\n"
        "# User Brief JSON\n\n"
        f"```json\n{brief_json}\n```\n\n"
        "# Proposal Draft JSON\n\n"
        f"```json\n{draft_json}\n```"
    )


def parse_critique_report(raw_output: str) -> CritiqueReport:
    """Parse and validate the raw LLM JSON output as ``CritiqueReport``.

    Args:
        raw_output: JSON string returned by the BasicCritic LLM.

    Returns:
        A validated ``CritiqueReport`` instance.

    Raises:
        ValueError: If the output is not valid JSON or fails Pydantic validation.
    """
    try:
        return CritiqueReport.model_validate_json(raw_output)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Invalid CritiqueReport output: {exc}") from exc


def basic_critic_node(
    state: WorkflowState,
    llm_client: BasicCriticLLM | None = None,
) -> WorkflowState:
    """Call the LLM critic and save a validated critique report to state.

    This node reviews the assembled proposal draft for logic gaps, evidence
    gaps, and unclear financial assumptions. It only reports issues; it does
    not rewrite the proposal (that is the RevisionNode's job) and calls no
    tools beyond the LLM.

    Args:
        state: Current workflow state. Expected to contain ``user_brief`` and
            ``proposal_draft``.
        llm_client: Optional test or production LLM adapter implementing
            ``generate_json(prompt: str) -> str``.

    Returns:
        A partial state update with ``critique_report`` and ``current_step``.
    """
    if llm_client is None:
        from workflow.llm import create_default_basic_critic_llm

        llm_client = create_default_basic_critic_llm()

    proposal_draft = state.get("proposal_draft")
    if proposal_draft is None:
        raise ValueError("basic_critic_node requires proposal_draft in state.")

    user_brief = state.get("user_brief") or {}
    prompt = build_basic_critic_prompt(user_brief, proposal_draft)
    raw_output = llm_client.generate_json(prompt)
    critique_report = parse_critique_report(raw_output)

    return {
        "critique_report": critique_report.model_dump(),
        "current_step": "basic_critic",
    }
