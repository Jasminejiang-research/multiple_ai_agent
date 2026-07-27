"""SLM-backed adapter factories for existing workflow injection points."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.workflow import (
    CritiqueReport,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
    ProposalOutline,
    RevisedProposal,
    SectionDraft,
    SectionDrafts,
)
from workflow.llm_client import (
    StructuredJsonLLM,
    StructuredOutputValidationError,
)

from slm.client import SLMClient
from slm.config import SLMConfig


SECTION_BATCHES = (
    PROPOSAL_SECTION_TITLES[:5],
    PROPOSAL_SECTION_TITLES[5:9],
    PROPOSAL_SECTION_TITLES[9:],
)


class _SectionDraftBatch(BaseModel):
    """A bounded subset of SectionDrafts used by the 3B fallback."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    proposal_title: Annotated[
        str,
        Field(min_length=2, max_length=120),
    ]
    sections: Annotated[
        list[SectionDraft],
        Field(min_length=4, max_length=5),
    ]
    writing_notes: Annotated[
        list[str],
        Field(default_factory=list, max_length=2),
    ]


class ChunkedSectionAdapter(StructuredJsonLLM):
    """Generate the 13 SectionDrafts as three smaller validated requests."""

    def __init__(
        self,
        client: SLMClient,
        *,
        temperature: float = 0.3,
    ) -> None:
        super().__init__(
            client,
            SectionDrafts,
            temperature=temperature,
        )
        self._batch_adapter = StructuredJsonLLM(
            client,
            _SectionDraftBatch,
            temperature=temperature,
        )

    @staticmethod
    def _batch_prompt(
        prompt: str,
        *,
        batch_index: int,
        section_titles: tuple[str, ...],
        proposal_title: str | None,
    ) -> str:
        title_instruction = (
            "\nUse this exact proposal_title for consistency: "
            f"{json.dumps(proposal_title, ensure_ascii=False)}."
            if proposal_title is not None
            else ""
        )
        return (
            f"{prompt}\n\n"
            "# SLM Chunked Section Generation\n\n"
            f"This is batch {batch_index + 1} of {len(SECTION_BATCHES)}. "
            "Generate exactly the sections listed below, in this order. "
            "For this request, this batch instruction replaces any earlier "
            "instruction to generate all 13 sections. Return no sections from "
            "another batch."
            f"{title_instruction}\n\n"
            f"{json.dumps(section_titles, ensure_ascii=False)}"
        )

    @staticmethod
    def _batch_validator(
        section_titles: tuple[str, ...],
    ) -> Callable[[BaseModel], None]:
        def validate(candidate: BaseModel) -> None:
            batch = _SectionDraftBatch.model_validate(candidate)
            actual_titles = tuple(section.title for section in batch.sections)
            if actual_titles != section_titles:
                raise ValueError(
                    "Section batch titles must match exactly and in order: "
                    f"{section_titles!r}; got {actual_titles!r}."
                )

        return validate

    @staticmethod
    def _validate_final_output(
        result: SectionDrafts,
        output_validator: Callable[[BaseModel], None] | None,
    ) -> None:
        if output_validator is None:
            return
        try:
            output_validator(result)
        except ValueError as exc:
            raise StructuredOutputValidationError(
                f"Invalid SectionDrafts output: {exc}"
            ) from exc

    def _generate_batches(
        self,
        prompt: str,
        *,
        allow_correction: bool,
    ) -> SectionDrafts:
        batches: list[_SectionDraftBatch] = []
        proposal_title: str | None = None

        for batch_index, section_titles in enumerate(SECTION_BATCHES):
            batch_prompt = self._batch_prompt(
                prompt,
                batch_index=batch_index,
                section_titles=section_titles,
                proposal_title=proposal_title,
            )
            validator = self._batch_validator(section_titles)
            if allow_correction:
                raw_batch = self._batch_adapter.generate_json_validated(
                    batch_prompt,
                    validator,
                )
            else:
                raw_batch = self._batch_adapter.generate_json_once(
                    batch_prompt,
                    validator,
                )
            batch = _SectionDraftBatch.model_validate_json(raw_batch)
            batches.append(batch)
            if proposal_title is None:
                proposal_title = batch.proposal_title

        writing_notes = list(
            dict.fromkeys(
                note
                for batch in batches
                for note in batch.writing_notes
            )
        )
        return SectionDrafts.model_validate(
            {
                "proposal_title": proposal_title,
                "sections": [
                    section.model_dump()
                    for batch in batches
                    for section in batch.sections
                ],
                "writing_notes": writing_notes,
            }
        )

    def generate_json(self, prompt: str) -> str:
        """Return three corrected batch calls merged as complete SectionDrafts."""
        return self._generate_batches(
            prompt,
            allow_correction=True,
        ).model_dump_json()

    def generate_json_validated(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None],
    ) -> str:
        """Apply batch validation and then the caller's whole-output validator."""
        result = self._generate_batches(prompt, allow_correction=True)
        self._validate_final_output(result, output_validator)
        return result.model_dump_json()

    def generate_json_once(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None] | None = None,
    ) -> str:
        """Generate each of three batches once, without correction requests."""
        result = self._generate_batches(prompt, allow_correction=False)
        self._validate_final_output(result, output_validator)
        return result.model_dump_json()

    def generate_json_for_schema_once(
        self,
        prompt: str,
        schema: type[BaseModel],
        output_validator: Callable[[BaseModel], None] | None = None,
    ) -> str:
        """Use chunking for SectionDrafts and delegate other one-shot schemas."""
        if schema is SectionDrafts:
            return self.generate_json_once(prompt, output_validator)
        return super().generate_json_for_schema_once(
            prompt,
            schema,
            output_validator,
        )


def build_slm_adapters(config: SLMConfig) -> dict[str, StructuredJsonLLM]:
    """Build all adapters accepted by the existing graph injection seams."""

    slm_client = SLMClient(config)
    adapter_specs = {
        "planner": (ProposalOutline, 0.2),
        "section_writer": (SectionDrafts, 0.3),
        "basic_critic": (CritiqueReport, 0.2),
        "revision": (RevisedProposal, 0.2),
        "research": (ResearchAnalysis, 0.2),
        "strategy": (StrategyAnalysis, 0.2),
        "finance": (FinanceAssumptions, 0.2),
        "writer": (ProposalDraft, 0.2),
        "critic": (CritiqueReport, 0.2),
    }
    adapters = {
        name: StructuredJsonLLM(slm_client, schema, temperature=temperature)
        for name, (schema, temperature) in adapter_specs.items()
    }
    adapters["section_writer"] = ChunkedSectionAdapter(
        slm_client,
        temperature=0.3,
    )
    return adapters
