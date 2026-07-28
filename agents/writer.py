"""Writer Agent for assembling validated analysis into a proposal draft."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from agents.base import AgentLogHook, BaseAgent
from rag.citation_checker import (
    CitationFailure,
    collect_proposal_citation_failures,
    validate_proposal_citations,
    validate_proposal_source_allowlist,
)
from schemas.agent_outputs import WriterInput
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    ProposalDraft,
    RevisedProposalPatch,
)
from workflow.generation_batches import (
    PROPOSAL_DRAFT_BATCH_MODELS,
    PROPOSAL_SECTION_BATCHES,
    merge_proposal_draft_batches,
)
from workflow.llm_client import (
    StructuredJsonLLM,
    StructuredOutputValidationError,
    create_default_llm_client,
)

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


def build_writer_batch_prompt(
    prompt: str,
    *,
    batch_number: int,
    section_fields: tuple[str, ...],
    schema_name: str,
    include_title: bool,
) -> str:
    """Append the authoritative generation-only shape for one section batch."""
    top_level_fields = (
        f"`title` and exactly these section fields: {', '.join(section_fields)}"
        if include_title
        else f"exactly these section fields: {', '.join(section_fields)}"
    )
    return (
        f"{prompt}\n\n"
        "# Authoritative Section Batch Override\n\n"
        f"This is batch {batch_number} of {len(PROPOSAL_SECTION_BATCHES)}. "
        "Generate only the sections assigned to this batch. This instruction "
        "overrides earlier output-shape text that requests all 13 sections or "
        "`global_source_ids`; those values are assembled deterministically "
        "after all batches validate.\n\n"
        f"Return one `{schema_name}` JSON object with {top_level_fields}. Do not "
        "return any other proposal section or wrapper object. Keep each section "
        "concise enough to finish the complete batch: use 2-4 short paragraphs "
        "and no more than 4 non-duplicative key claims unless essential."
    )


def build_writer_citation_patch_prompt(
    prompt: str,
    proposal: ProposalDraft,
    failures: list[CitationFailure],
) -> str:
    """Request replacements for only the sections that failed final citations."""
    failed_sections = list(dict.fromkeys(failure.section for failure in failures))
    section_payload = {
        section_name: getattr(proposal, section_name).model_dump()
        for section_name in failed_sections
    }
    return (
        f"{prompt}\n\n"
        "# Final Writer Citation Patch\n\n"
        "The four section batches were schema-valid, but the complete merged "
        "ProposalDraft failed citation validation. Return a "
        "`RevisedProposalPatch` containing exactly the failed sections below "
        "and no other section. Preserve or add an exact `[source_id]` marker in "
        "both the anchored prose sentence and claim text for every sourced_fact. "
        "Use only source IDs supplied in Writer Input JSON. If direct support is "
        "absent, downgrade the claim to assumption/unsupported/needs_validation, "
        "clear unsupported source IDs, use cautious wording, and set confidence "
        "to low.\n\n"
        "# Complete CitationFailure JSON\n\n"
        "```json\n"
        f"{json.dumps([failure.model_dump() for failure in failures], ensure_ascii=False, indent=2)}"
        "\n```\n\n"
        "# Failed Sections JSON\n\n"
        f"```json\n{json.dumps(section_payload, ensure_ascii=False, indent=2)}\n```"
    )


def _remove_source_markers(text: str, source_ids: set[str]) -> str:
    """Remove only exact markers for source IDs rejected by the allowlist."""
    cleaned = text
    for source_id in source_ids:
        cleaned = cleaned.replace(f"[{source_id}]", "")
    return " ".join(cleaned.split())


def downgrade_failed_writer_citations(
    proposal: ProposalDraft,
    failures: list[CitationFailure],
) -> ProposalDraft:
    """Safely downgrade claims that remain invalid after the final patch."""
    proposal_data = proposal.model_dump()
    for failure in failures:
        section_data = proposal_data[failure.section]
        unknown_ids = set(failure.unknown_source_ids)
        if unknown_ids:
            section_data["content"] = _remove_source_markers(
                section_data["content"],
                unknown_ids,
            )
            section_data["source_ids"] = [
                source_id
                for source_id in section_data["source_ids"]
                if source_id not in unknown_ids
            ]
        if failure.claim_index >= 0:
            claim = section_data["key_claims"][failure.claim_index]
            claim["text"] = _remove_source_markers(
                claim["text"],
                unknown_ids,
            )
            claim["content_anchor"] = _remove_source_markers(
                claim["content_anchor"],
                unknown_ids,
            )
            claim["evidence_status"] = "needs_validation"
            claim["source_ids"] = []
        section_data["confidence"] = "low"
    return ProposalDraft.model_validate(proposal_data)


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
    """Reject source IDs absent from the supplied RAG and web evidence."""
    allowed_source_ids = {
        chunk.source_id for chunk in writer_input.evidence_chunks
    }
    allowed_source_ids.update(source.source_id for source in writer_input.web_sources)
    validate_proposal_source_allowlist(
        proposal,
        allowed_source_ids,
        output_name="ProposalDraft",
    )


def apply_evidence_confidence_floor(
    proposal: ProposalDraft,
    writer_input: WriterInput,
) -> ProposalDraft:
    """Deterministically expose degraded evidence through section confidence."""
    if not writer_input.low_confidence_required:
        return proposal
    for field_name in PROPOSAL_SECTION_FIELD_NAMES:
        section = getattr(proposal, field_name)
        if writer_input.evidence_mode == "no_external_evidence" or not section.source_ids:
            section.confidence = "low"
    return proposal


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
        allowed_source_ids = {
            chunk.source_id for chunk in writer_input.evidence_chunks
        }
        allowed_source_ids.update(
            source.source_id for source in writer_input.web_sources
        )

        def validate_writer_output(candidate: ProposalDraft) -> None:
            """Aggregate unknown IDs and missing markers in one correction."""
            validate_proposal_citations(
                ProposalDraft.model_validate(candidate),
                allowed_source_ids=allowed_source_ids,
                output_name="ProposalDraft",
            )

        batch_generator = getattr(
            llm_client,
            "generate_json_for_schema",
            None,
        )
        if callable(batch_generator):
            batch_outputs = []
            for batch_number, (section_fields, batch_model) in enumerate(
                zip(
                    PROPOSAL_SECTION_BATCHES,
                    PROPOSAL_DRAFT_BATCH_MODELS,
                    strict=True,
                ),
                start=1,
            ):
                batch_prompt = build_writer_batch_prompt(
                    prompt,
                    batch_number=batch_number,
                    section_fields=section_fields,
                    schema_name=batch_model.__name__,
                    include_title="title" in batch_model.model_fields,
                )

                raw_batch = batch_generator(
                    batch_prompt,
                    batch_model,
                )
                batch_outputs.append(batch_model.model_validate_json(raw_batch))
            proposal = merge_proposal_draft_batches(batch_outputs)
            failures = collect_proposal_citation_failures(
                proposal,
                allowed_source_ids=allowed_source_ids,
            )
            if failures:
                failed_sections = {failure.section for failure in failures}
                patch_prompt = build_writer_citation_patch_prompt(
                    prompt,
                    proposal,
                    failures,
                )

                def validate_writer_patch(candidate: Any) -> None:
                    patch_candidate = RevisedProposalPatch.model_validate(candidate)
                    patched_sections = {
                        section_patch.section
                        for section_patch in patch_candidate.sections
                    }
                    if patched_sections != failed_sections:
                        raise ValueError(
                            "Writer citation patch must contain exactly the "
                            "failed sections: "
                            + ", ".join(sorted(failed_sections))
                        )
                    candidate_data = proposal.model_dump()
                    for section_patch in patch_candidate.sections:
                        candidate_data[section_patch.section] = (
                            section_patch.replacement.model_dump()
                        )
                    validate_proposal_citations(
                        ProposalDraft.model_validate(candidate_data),
                        allowed_source_ids=allowed_source_ids,
                        output_name="ProposalDraft",
                    )

                try:
                    raw_patch = batch_generator(
                        patch_prompt,
                        RevisedProposalPatch,
                        validate_writer_patch,
                    )
                    patch = RevisedProposalPatch.model_validate_json(raw_patch)
                    proposal_data = proposal.model_dump()
                    for section_patch in patch.sections:
                        proposal_data[section_patch.section] = (
                            section_patch.replacement.model_dump()
                        )
                    proposal = ProposalDraft.model_validate(proposal_data)
                except StructuredOutputValidationError:
                    proposal = downgrade_failed_writer_citations(
                        proposal,
                        failures,
                    )
        else:
            validated_generator = getattr(
                llm_client,
                "generate_json_validated",
                None,
            )
            if callable(validated_generator):
                raw_output = validated_generator(prompt, validate_writer_output)
            else:
                raw_output = llm_client.generate_json(prompt)
            proposal = parse_proposal_draft(raw_output)

        proposal = apply_evidence_confidence_floor(proposal, writer_input)
        validate_writer_output(proposal)
        return proposal
