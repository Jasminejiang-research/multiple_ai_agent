"""Tests for slim-schema generation with deterministic expansion."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from pydantic import BaseModel

import slm.factories as factories_module
from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.workflow import PROPOSAL_SECTION_TITLES, ProposalDraft
from slm.config import SLMConfig
from slm.factories import ChunkedProposalAdapter, PrunedAdapter, build_slm_adapters
from slm.pruning import (
    ASSUMPTION_NOTICE,
    PRUNED_SPECS,
    SlimFinanceAssumptions,
    SlimResearchAnalysis,
    condense_prompt,
    expand_finance,
    expand_research,
)

_SENTENCE = "A concise, well-grounded statement about the smart ring market."
_LONG_TEXT = (
    "Section content long enough to satisfy the strict minimum length "
    "constraint of the full proposal schema."
)


def _slim_finding() -> dict[str, str]:
    return {"topic": "Market", "finding": _SENTENCE, "rationale": _SENTENCE}


def _slim_research_payload() -> dict[str, Any]:
    return {
        "analysis_summary": _SENTENCE,
        "market_trends": [_slim_finding()],
        "customer_notes": [_slim_finding()],
        "competitor_assumptions": [_slim_finding()],
    }


def _slim_finance_payload() -> dict[str, Any]:
    item = {"topic": "Pricing", "assumption": _SENTENCE, "rationale": _SENTENCE}
    return {
        "analysis_summary": _SENTENCE,
        "revenue_assumptions": [item],
        "cost_assumptions": [item],
        "unit_economics_assumptions": [item],
        "break_even_discussion": _SENTENCE,
    }


def test_condense_prompt_strips_schema_and_quality_sections() -> None:
    prompt = (
        "# Role\n\nYou are an agent.\n\n"
        "# Output Schema\n\nReturn valid JSON.\n\n```json\n{\"a\": 1}\n```\n\n"
        "# Quality Criteria\n\n- be great\n\n"
        "# Failure Behavior\n\nStill return JSON."
    )

    condensed = condense_prompt(prompt)

    assert "# Role" in condensed
    assert "# Failure Behavior" in condensed
    assert "# Output Schema" not in condensed
    assert '{"a": 1}' not in condensed
    assert "# Quality Criteria" not in condensed
    assert "# Output Brevity (SLM)" in condensed


def test_expansion_fills_only_defaults_and_documented_boilerplate() -> None:
    research = expand_research(
        SlimResearchAnalysis.model_validate(_slim_research_payload())
    )
    assert isinstance(research, ResearchAnalysis)
    assert research.unsupported_claims == []
    assert research.needs_human_review == []

    finance = expand_finance(
        SlimFinanceAssumptions.model_validate(_slim_finance_payload())
    )
    assert isinstance(finance, FinanceAssumptions)
    # The one synthesized value: fixed boilerplate the schema validator demands.
    assert finance.assumption_notice == ASSUMPTION_NOTICE


@pytest.mark.parametrize(
    ("name", "spec"),
    list(PRUNED_SPECS.items()),
)
def test_every_pruned_spec_expands_to_its_full_schema(name, spec) -> None:
    full_schema, slim_schema, expander = spec
    payloads = {
        "research": _slim_research_payload,
        "strategy": lambda: {
            "analysis_summary": _SENTENCE,
            **{
                field: [
                    {
                        "topic": "Topic",
                        "recommendation": _SENTENCE,
                        "rationale": _SENTENCE,
                    }
                ]
                for field in (
                    "value_proposition",
                    "business_model_logic",
                    "gtm_strategy",
                    "moat_hypotheses",
                )
            },
        },
        "finance": _slim_finance_payload,
    }

    expanded = expander(slim_schema.model_validate(payloads[name]()))

    assert isinstance(expanded, full_schema)


class _FakeSlimClient:
    """Serves slim payloads and records every request prompt and schema."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    def _serve(self, method: str, prompt: str, schema, **kwargs):
        self.calls.append({"method": method, "prompt": prompt, "schema": schema})
        result = schema.model_validate(self._payload)
        validator = kwargs.get("output_validator")
        if validator is not None:
            validator(result)
        return result

    def generate_structured(self, prompt, schema, **kwargs):
        return self._serve("corrected", prompt, schema, **kwargs)

    def generate_structured_once(self, prompt, schema, **kwargs):
        return self._serve("once", prompt, schema, **kwargs)


def test_pruned_adapter_requests_slim_and_returns_full_json() -> None:
    client = _FakeSlimClient(_slim_research_payload())
    full_schema, slim_schema, expander = PRUNED_SPECS["research"]
    adapter = PrunedAdapter(
        client,  # type: ignore[arg-type]
        full_schema,
        slim_schema,
        expander,
    )
    prompt = "# Role\n\nAnalyse.\n\n# Output Schema\n\n{\"full\": true}\n"

    raw = adapter.generate_json(prompt)

    # The model was asked for the slim schema with a condensed prompt...
    assert client.calls[0]["schema"] is slim_schema
    assert "# Output Schema" not in client.calls[0]["prompt"]
    assert "# Output Brevity (SLM)" in client.calls[0]["prompt"]
    # ...and the caller received JSON valid under the full schema.
    result = ResearchAnalysis.model_validate_json(raw)
    assert result.market_trends[0].topic == "Market"


def test_pruned_adapter_runs_the_callers_full_schema_validator() -> None:
    client = _FakeSlimClient(_slim_research_payload())
    full_schema, slim_schema, expander = PRUNED_SPECS["research"]
    adapter = PrunedAdapter(
        client,  # type: ignore[arg-type]
        full_schema,
        slim_schema,
        expander,
    )
    seen: list[BaseModel] = []

    adapter.generate_json_validated("Analyse.", seen.append)

    assert len(seen) == 1
    assert isinstance(seen[0], ResearchAnalysis)


def test_slim_writer_batches_expand_to_a_complete_proposal() -> None:
    class _FakeBatchClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def _serve(self, prompt: str, schema, **kwargs):
            self.calls.append({"prompt": prompt, "schema": schema})
            payload: dict[str, Any] = {"title": "Smart Ring Proposal"}
            for field_name in schema.model_fields:
                if field_name == "title":
                    continue
                payload[field_name] = {
                    "title": PROPOSAL_SECTION_TITLES[
                        factories_module.PROPOSAL_SECTION_FIELD_NAMES.index(
                            field_name
                        )
                    ],
                    "content": _LONG_TEXT,
                }
            result = schema.model_validate(payload)
            validator = kwargs.get("output_validator")
            if validator is not None:
                validator(result)
            return result

        generate_structured = _serve
        generate_structured_once = _serve

    client = _FakeBatchClient()
    adapter = ChunkedProposalAdapter(
        client,  # type: ignore[arg-type]
        slim=True,
    )

    raw = adapter.generate_json("# Role\n\nWrite.\n\n# Output Schema\n\nfull\n")

    draft = ProposalDraft.model_validate_json(raw)
    assert draft.title == "Smart Ring Proposal"
    # Slim batch schemas were used, and pruned defaults filled the rest.
    assert all(
        call["schema"].__name__.startswith("SlimProposalDraftBatch_")
        for call in client.calls
    )
    assert draft.executive_summary.key_claims == []
    assert draft.executive_summary.confidence == "medium"
    assert all(
        "# Output Brevity (SLM)" in call["prompt"] for call in client.calls
    )


def test_pruning_is_opt_in_and_leaves_critic_and_revision_alone() -> None:
    config = SLMConfig(
        base_url="https://api.siliconflow.com/v1",
        model_name="Qwen/Qwen2.5-7B-Instruct",
        api_key="test",
        structured_mode="json_object",
        max_prompt_chars=90_000,
        max_output_tokens=4_096,
        run_max_requests=18,
        run_max_total_tokens=300_000,
        request_timeout=300,
        chunked_writer=True,
        pruned_schemas=True,
    )
    pruned = build_slm_adapters(config)
    plain = build_slm_adapters(
        dataclasses.replace(config, pruned_schemas=False)
    )

    for name in ("research", "strategy", "finance"):
        assert isinstance(pruned[name], PrunedAdapter)
        assert not isinstance(plain[name], PrunedAdapter)
    # Short-output nodes keep the full schemas and the upstream protocols.
    assert not isinstance(pruned["critic"], PrunedAdapter)
    assert not isinstance(pruned["revision"], PrunedAdapter)
    assert pruned["writer"]._slim is True
    assert plain["writer"]._slim is False
