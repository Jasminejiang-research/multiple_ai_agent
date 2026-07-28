"""Tests for generation-only proposal and revision section batches."""

from __future__ import annotations

from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
    RevisedProposal,
)
from workflow.generation_batches import (
    PROPOSAL_DRAFT_BATCH_MODELS,
    PROPOSAL_SECTION_BATCHES,
    REVISED_PROPOSAL_BATCH_MODELS,
    merge_proposal_draft_batches,
    merge_revised_proposal_batches,
)


def _proposal() -> ProposalDraft:
    payload: dict[str, object] = {"title": "Batched Proposal"}
    for title, field_name in zip(
        PROPOSAL_SECTION_TITLES,
        PROPOSAL_SECTION_FIELD_NAMES,
        strict=True,
    ):
        payload[field_name] = {
            "title": title,
            "content": (
                f"The {title} section is generated in one small validated batch "
                "and merged deterministically afterward."
            ),
            "key_claims": [],
            "source_ids": [],
            "confidence": "low",
        }
    return ProposalDraft.model_validate(payload)


def _batch_payloads(
    proposal: ProposalDraft,
    batch_models: tuple[type, ...],
    *,
    revision: RevisedProposal | None = None,
) -> list[dict[str, object]]:
    proposal_payload = proposal.model_dump()
    payloads: list[dict[str, object]] = []
    for model in batch_models:
        payload: dict[str, object] = {
            field_name: proposal_payload[field_name]
            for field_name in model.model_fields
            if field_name in proposal_payload
        }
        if revision is not None:
            for metadata_field in (
                "applied_critique_summary",
                "unresolved_issues",
            ):
                if metadata_field in model.model_fields:
                    payload[metadata_field] = getattr(
                        revision,
                        metadata_field,
                    )
        payloads.append(payload)
    return payloads


def test_section_batches_cover_all_fields_once_in_4_3_3_3_groups() -> None:
    assert tuple(map(len, PROPOSAL_SECTION_BATCHES)) == (4, 3, 3, 3)
    assert tuple(
        field_name
        for batch in PROPOSAL_SECTION_BATCHES
        for field_name in batch
    ) == PROPOSAL_SECTION_FIELD_NAMES


def test_proposal_batches_merge_and_rebuild_global_source_ids() -> None:
    proposal = _proposal()
    proposal.executive_summary.source_ids = ["source-a"]
    payloads = _batch_payloads(proposal, PROPOSAL_DRAFT_BATCH_MODELS)

    merged = merge_proposal_draft_batches(payloads)

    assert isinstance(merged, ProposalDraft)
    assert merged.global_source_ids == ["source-a"]
    assert merged.appendix.title == "Appendix"


def test_only_first_batch_owns_the_proposal_title() -> None:
    assert "title" in PROPOSAL_DRAFT_BATCH_MODELS[0].model_fields
    assert all(
        "title" not in model.model_fields
        for model in PROPOSAL_DRAFT_BATCH_MODELS[1:]
    )
    assert "title" in REVISED_PROPOSAL_BATCH_MODELS[0].model_fields
    assert all(
        "title" not in model.model_fields
        for model in REVISED_PROPOSAL_BATCH_MODELS[1:]
    )


def test_revision_batches_merge_metadata_and_full_proposal() -> None:
    proposal = _proposal()
    revision = RevisedProposal(
        proposal=proposal,
        applied_critique_summary=["Clarified the financial basis."],
        unresolved_issues=["Validate pricing evidence."],
    )
    payloads = _batch_payloads(
        proposal,
        REVISED_PROPOSAL_BATCH_MODELS,
        revision=revision,
    )

    merged = merge_revised_proposal_batches(payloads)

    assert merged == revision
    assert merged.proposal.financial_assumptions.title == "Financial Assumptions"
