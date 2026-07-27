"""Tests for SLM adapters bound to existing workflow schemas."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

import slm.factories as factories_module
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
    SectionDrafts,
)
from slm.config import SLMConfig
from slm.factories import ChunkedSectionAdapter, SECTION_BATCHES, build_slm_adapters
from workflow.llm_client import StructuredJsonLLM


EXPECTED_ADAPTERS = {
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


@pytest.fixture
def config() -> SLMConfig:
    return SLMConfig(
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:3b",
        api_key="ollama",
        structured_mode="json_object",
        max_prompt_chars=60_000,
        max_output_tokens=8_192,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=300,
    )


@pytest.fixture
def adapters(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
) -> dict[str, StructuredJsonLLM]:
    shared_client = object()
    created_with: list[SLMConfig] = []

    def fake_slm_client(received_config: SLMConfig) -> object:
        created_with.append(received_config)
        return shared_client

    monkeypatch.setattr(factories_module, "SLMClient", fake_slm_client)
    built_adapters = build_slm_adapters(config)

    assert created_with == [config]
    assert {adapter._client for adapter in built_adapters.values()} == {
        shared_client
    }
    return built_adapters


def test_build_slm_adapters_covers_all_injection_points(
    adapters: dict[str, StructuredJsonLLM],
) -> None:
    assert set(adapters) == set(EXPECTED_ADAPTERS)
    assert all(isinstance(adapter, StructuredJsonLLM) for adapter in adapters.values())
    assert isinstance(adapters["section_writer"], ChunkedSectionAdapter)


@pytest.mark.parametrize(
    ("adapter_name", "expected_schema", "expected_temperature"),
    [
        (adapter_name, schema, temperature)
        for adapter_name, (schema, temperature) in EXPECTED_ADAPTERS.items()
    ],
)
def test_build_slm_adapters_matches_existing_defaults(
    adapters: dict[str, StructuredJsonLLM],
    adapter_name: str,
    expected_schema: type,
    expected_temperature: float,
) -> None:
    adapter = adapters[adapter_name]

    assert adapter._schema is expected_schema
    assert adapter._temperature == expected_temperature


class _AlternativeOutput(BaseModel):
    value: str


class _FakeStructuredClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def _generate(
        self,
        method: str,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        batch_index = len(
            [
                call
                for call in self.calls
                if call["schema"] is factories_module._SectionDraftBatch
            ]
        )
        self.calls.append(
            {
                "method": method,
                "prompt": prompt,
                "schema": schema,
                **kwargs,
            }
        )
        if schema is factories_module._SectionDraftBatch:
            titles = SECTION_BATCHES[batch_index]
            result = schema.model_validate(
                {
                    "proposal_title": "AI Education Proposal",
                    "sections": [
                        {
                            "title": title,
                            "content": (
                                f"{title} content grounded in the supplied "
                                "brief and proposal outline for validation."
                            ),
                            "key_claims": [],
                            "source_ids": [],
                            "confidence": "medium",
                        }
                        for title in titles
                    ],
                    "writing_notes": [f"batch {batch_index + 1} note"],
                }
            )
        else:
            result = schema.model_validate({"value": "ok"})

        output_validator = kwargs.get("output_validator")
        if output_validator is not None:
            output_validator(result)
        return result

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        return self._generate("corrected", prompt, schema, **kwargs)

    def generate_structured_once(
        self,
        prompt: str,
        schema: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        return self._generate("once", prompt, schema, **kwargs)


def test_chunked_section_adapter_merges_three_validated_batches() -> None:
    client = _FakeStructuredClient()
    adapter = ChunkedSectionAdapter(client)  # type: ignore[arg-type]

    result = SectionDrafts.model_validate_json(adapter.generate_json("base prompt"))

    assert tuple(section.title for section in result.sections) == (
        PROPOSAL_SECTION_TITLES
    )
    assert result.writing_notes == [
        "batch 1 note",
        "batch 2 note",
        "batch 3 note",
    ]
    assert [call["method"] for call in client.calls] == ["corrected"] * 3
    assert all(
        "# SLM Chunked Section Generation" in call["prompt"]
        for call in client.calls
    )
    assert "batch 1 of 3" in client.calls[0]["prompt"]
    assert "Use this exact proposal_title" in client.calls[1]["prompt"]


def test_chunked_section_adapter_supports_all_structured_adapter_methods() -> None:
    client = _FakeStructuredClient()
    adapter = ChunkedSectionAdapter(client)  # type: ignore[arg-type]
    validated: list[BaseModel] = []

    validated_result = adapter.generate_json_validated(
        "validated prompt",
        validated.append,
    )
    assert SectionDrafts.model_validate_json(validated_result)
    assert len(validated) == 1

    client.calls.clear()
    once_result = adapter.generate_json_once("one shot prompt")
    assert SectionDrafts.model_validate_json(once_result)
    assert [call["method"] for call in client.calls] == ["once"] * 3

    client.calls.clear()
    alternate_result = adapter.generate_json_for_schema_once(
        "alternate prompt",
        _AlternativeOutput,
    )
    assert _AlternativeOutput.model_validate_json(alternate_result).value == "ok"
    assert len(client.calls) == 1
    assert client.calls[0]["method"] == "once"
    assert client.calls[0]["schema"] is _AlternativeOutput
