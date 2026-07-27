"""Tests for SLM adapters bound to existing workflow schemas."""

from __future__ import annotations

import pytest

import slm.factories as factories_module
from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.workflow import (
    CritiqueReport,
    ProposalDraft,
    ProposalOutline,
    RevisedProposal,
    SectionDrafts,
)
from slm.config import SLMConfig
from slm.factories import build_slm_adapters
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
