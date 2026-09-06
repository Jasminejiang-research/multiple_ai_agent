"""SLM-backed adapter factories for existing workflow injection points."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, create_model

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.workflow import (
    CritiqueReport,
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
    ProposalOutline,
    ProposalSection,
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
from slm.pruning import (
    PRUNED_SPECS,
    SlimProposalSection,
    condense_prompt,
)


_BATCH_BOUNDARIES = ((0, 5), (5, 9), (9, len(PROPOSAL_SECTION_TITLES)))

SECTION_BATCHES = tuple(
    PROPOSAL_SECTION_TITLES[start:stop] for start, stop in _BATCH_BOUNDARIES
)
# ProposalDraft holds the same 13 sections as named object fields rather than a
# list, so the writer batches are expressed as field names on the same split.
PROPOSAL_FIELD_BATCHES = tuple(
    PROPOSAL_SECTION_FIELD_NAMES[start:stop] for start, stop in _BATCH_BOUNDARIES
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


class PrunedAdapter(StructuredJsonLLM):
    """Generate against a slim schema, expand deterministically to the full one.

    The expansion runs inside the slim request's ``output_validator``, so an
    expansion that fails full-schema validation shares the client's single
    correction attempt instead of failing without recourse.
    """

    def __init__(
        self,
        client: SLMClient,
        full_schema: type[BaseModel],
        slim_schema: type[BaseModel],
        expander: Callable[[BaseModel], BaseModel],
        *,
        temperature: float = 0.2,
    ) -> None:
        super().__init__(client, full_schema, temperature=temperature)
        self._slim_adapter = StructuredJsonLLM(
            client, slim_schema, temperature=temperature
        )
        self._slim_schema = slim_schema
        self._expander = expander

    def _expand_checked(self, slim: BaseModel) -> None:
        """Raise ``ValueError`` (shared correction) when expansion cannot pass."""
        self._expander(self._slim_schema.model_validate(slim))

    def _generate_full(self, prompt: str, *, once: bool) -> str:
        slim_prompt = condense_prompt(prompt)
        if once:
            raw_slim = self._slim_adapter.generate_json_once(
                slim_prompt, self._expand_checked
            )
        else:
            raw_slim = self._slim_adapter.generate_json_validated(
                slim_prompt, self._expand_checked
            )
        slim = self._slim_schema.model_validate_json(raw_slim)
        return self._expander(slim).model_dump_json()

    def generate_json(self, prompt: str) -> str:
        """Return full-schema JSON grown from one corrected slim request."""
        return self._generate_full(prompt, once=False)

    def generate_json_validated(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None],
    ) -> str:
        """Run the caller's full-schema validator on the expanded output.

        Same limitation as the chunked adapters: the whole-output validator
        gets no correction attempt of its own.
        """
        raw_full = self._generate_full(prompt, once=False)
        result = self._schema.model_validate_json(raw_full)
        try:
            output_validator(result)
        except ValueError as exc:
            raise StructuredOutputValidationError(
                f"Invalid {self._schema.__name__} output: {exc}"
            ) from exc
        return raw_full

    def generate_json_once(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None] | None = None,
    ) -> str:
        """One slim attempt, expanded, without a correction request."""
        raw_full = self._generate_full(prompt, once=True)
        if output_validator is not None:
            result = self._schema.model_validate_json(raw_full)
            try:
                output_validator(result)
            except ValueError as exc:
                raise StructuredOutputValidationError(
                    f"Invalid {self._schema.__name__} output: {exc}"
                ) from exc
        return raw_full


@lru_cache(maxsize=2 * len(PROPOSAL_FIELD_BATCHES))
def _proposal_batch_model(
    field_names: tuple[str, ...],
    slim: bool = False,
) -> type[BaseModel]:
    """Build a ProposalDraft subset model covering one batch of sections.

    ``global_source_ids`` is deliberately absent: ``ProposalDraft`` derives it
    from the section ``source_ids`` in its own validator, so asking a 3B model
    to maintain it per batch would only invite drift.

    The config mirrors ``ProposalDraft`` exactly, which notably does *not* set
    ``extra="forbid"``. Being stricter here would invent a failure mode the
    unchunked path does not have: a 3B model that volunteers an extra key would
    fail the batch even though ``ProposalDraft`` would ignore it. Sections
    belonging to other batches are harmless for the same reason -- the merge
    step reads only this batch's field names.

    With ``slim=True`` each section is a ``SlimProposalSection`` (title and
    content only); ``ProposalSection`` fills the dropped fields with their
    defaults when the merged draft is validated.
    """
    section_type: type[BaseModel] = (
        SlimProposalSection if slim else ProposalSection
    )
    return create_model(
        ("SlimProposalDraftBatch_" if slim else "ProposalDraftBatch_")
        + "_".join(field_names),
        __config__=ConfigDict(str_strip_whitespace=True),
        title=(
            Annotated[str, Field(min_length=2, max_length=120)],
            ...,
        ),
        **{field_name: (section_type, ...) for field_name in field_names},
    )


class ChunkedProposalAdapter(StructuredJsonLLM):
    """Generate the 13-section ProposalDraft as three smaller requests.

    The Writer node is unaware of the split: this still satisfies the
    ``generate_json``/``generate_json_validated`` contract it depends on.

    Known limitation, shared with :class:`ChunkedSectionAdapter`: the caller's
    whole-output validator (citation checking, for the Writer) runs on the
    merged draft and gets no correction attempt, because a correction would
    mean regenerating every batch.
    """

    def __init__(
        self,
        client: SLMClient,
        *,
        temperature: float = 0.2,
        slim: bool = False,
    ) -> None:
        super().__init__(client, ProposalDraft, temperature=temperature)
        self._client_for_batches = client
        self._temperature = temperature
        self._slim = slim

    def _batch_adapter(self, field_names: tuple[str, ...]) -> StructuredJsonLLM:
        return StructuredJsonLLM(
            self._client_for_batches,
            _proposal_batch_model(field_names, self._slim),
            temperature=self._temperature,
        )

    @staticmethod
    def _batch_prompt(
        prompt: str,
        *,
        batch_index: int,
        field_names: tuple[str, ...],
        proposal_title: str | None,
    ) -> str:
        expected_titles = {
            field_name: PROPOSAL_SECTION_TITLES[
                PROPOSAL_SECTION_FIELD_NAMES.index(field_name)
            ]
            for field_name in field_names
        }
        title_instruction = (
            "\nUse this exact title for consistency: "
            f"{json.dumps(proposal_title, ensure_ascii=False)}."
            if proposal_title is not None
            else ""
        )
        return (
            f"{prompt}\n\n"
            "# SLM Chunked Proposal Generation\n\n"
            f"This is batch {batch_index + 1} of {len(PROPOSAL_FIELD_BATCHES)}. "
            "Generate exactly the proposal fields listed below and no others. "
            "For this request, this batch instruction replaces any earlier "
            "instruction to generate all 13 sections. Each section's title must "
            "be exactly the value mapped to its field name."
            f"{title_instruction}\n\n"
            f"{json.dumps(expected_titles, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _batch_validator(
        field_names: tuple[str, ...],
    ) -> Callable[[BaseModel], None]:
        def validate(candidate: BaseModel) -> None:
            for field_name in field_names:
                expected_title = PROPOSAL_SECTION_TITLES[
                    PROPOSAL_SECTION_FIELD_NAMES.index(field_name)
                ]
                section = getattr(candidate, field_name)
                if section.title != expected_title:
                    raise ValueError(
                        f"ProposalDraft.{field_name} must have title "
                        f"{expected_title!r}; got {section.title!r}."
                    )

        return validate

    def _generate_batches(
        self,
        prompt: str,
        *,
        allow_correction: bool,
    ) -> ProposalDraft:
        merged: dict[str, object] = {}
        proposal_title: str | None = None
        base_prompt = condense_prompt(prompt) if self._slim else prompt

        for batch_index, field_names in enumerate(PROPOSAL_FIELD_BATCHES):
            batch_prompt = self._batch_prompt(
                base_prompt,
                batch_index=batch_index,
                field_names=field_names,
                proposal_title=proposal_title,
            )
            adapter = self._batch_adapter(field_names)
            validator = self._batch_validator(field_names)
            if allow_correction:
                raw_batch = adapter.generate_json_validated(
                    batch_prompt,
                    validator,
                )
            else:
                raw_batch = adapter.generate_json_once(batch_prompt, validator)
            batch = json.loads(raw_batch)
            if proposal_title is None:
                proposal_title = batch["title"]
            for field_name in field_names:
                merged[field_name] = batch[field_name]

        merged["title"] = proposal_title
        return ProposalDraft.model_validate(merged)

    @staticmethod
    def _validate_final_output(
        result: ProposalDraft,
        output_validator: Callable[[BaseModel], None] | None,
    ) -> None:
        if output_validator is None:
            return
        try:
            output_validator(result)
        except ValueError as exc:
            raise StructuredOutputValidationError(
                f"Invalid ProposalDraft output: {exc}"
            ) from exc

    def generate_json(self, prompt: str) -> str:
        """Return three corrected batch calls merged as one ProposalDraft."""
        return self._generate_batches(
            prompt,
            allow_correction=True,
        ).model_dump_json()

    def generate_json_validated(
        self,
        prompt: str,
        output_validator: Callable[[BaseModel], None],
    ) -> str:
        """Apply batch validation and then the caller's whole-draft validator."""
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
        """Use chunking for ProposalDraft and delegate other one-shot schemas."""
        if schema is ProposalDraft:
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
    if config.chunked_writer:
        adapters["writer"] = ChunkedProposalAdapter(
            slm_client,
            temperature=0.2,
            slim=config.pruned_schemas,
        )
    if config.pruned_schemas:
        # critic keeps the full schema (short output, and its severity and
        # issue_type judgments must come from the model); revision keeps the
        # upstream four-batch protocol whose batch models are defined and
        # validated by workflow/nodes.py.
        for name, (full_schema, slim_schema, expander) in PRUNED_SPECS.items():
            adapters[name] = PrunedAdapter(
                slm_client,
                full_schema,
                slim_schema,
                expander,
                temperature=0.2,
            )
    return adapters
