"""Offline size and keyword guards for Gemini generation schemas."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.proposal_schema import BusinessProposal
from schemas.workflow import (
    CritiqueReport,
    ProposalDraft,
    ProposalOutline,
    RevisedProposal,
    RevisedProposalPatch,
    SectionDrafts,
)
from workflow.gemini_schema import relaxed_response_schema

# Initial conservative budget from Phase 5 T2. After the live acceptance test
# in T3, replace this with 1.5 times the largest schema accepted by Gemini.
MAX_GENERATION_SCHEMA_CHARS = 15_000

# Every schema passed to LLMClient.generate_structured* in production.
# SupervisorPlan is intentionally absent: supervisor_agent_node constructs it
# deterministically and therefore never submits that schema to Gemini.
GENERATION_SCHEMAS = (
    BusinessProposal,
    ProposalOutline,
    SectionDrafts,
    CritiqueReport,
    RevisedProposal,
    RevisedProposalPatch,
    ProposalDraft,
    ResearchAnalysis,
    StrategyAnalysis,
    FinanceAssumptions,
)


def _iter_schema_keywords(node: Any) -> Iterator[str]:
    """Yield schema keywords without treating business property names as keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            if key == "properties" and isinstance(value, dict):
                for property_schema in value.values():
                    yield from _iter_schema_keywords(property_schema)
            else:
                yield from _iter_schema_keywords(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_schema_keywords(item)


def _iter_property_names(node: Any) -> Iterator[str]:
    """Yield every business field name declared by a schema fragment."""
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            yield from properties
        for value in node.values():
            yield from _iter_property_names(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_property_names(item)


@pytest.mark.parametrize(
    "model",
    GENERATION_SCHEMAS,
    ids=lambda model: model.__name__,
)
def test_generation_schema_stays_within_offline_budget(model: type) -> None:
    """Each production schema must remain small and structure-only."""
    generation_schema = relaxed_response_schema(model)
    serialized = json.dumps(generation_schema, sort_keys=True)
    schema_chars = len(serialized)
    context = f"{model.__name__} generation schema_chars={schema_chars}"

    schema_keywords = set(_iter_schema_keywords(generation_schema))
    forbidden_keywords = schema_keywords & {"description", "enum"}
    assert not forbidden_keywords, (
        f"{context} leaked forbidden keywords: {sorted(forbidden_keywords)}"
    )

    strict_property_names = set(_iter_property_names(model.model_json_schema()))
    generation_property_names = set(_iter_property_names(generation_schema))
    missing_properties = strict_property_names - generation_property_names
    assert not missing_properties, (
        f"{context} lost business properties: {sorted(missing_properties)}"
    )

    assert schema_chars < MAX_GENERATION_SCHEMA_CHARS, (
        f"{context} exceeds MAX_GENERATION_SCHEMA_CHARS="
        f"{MAX_GENERATION_SCHEMA_CHARS}"
    )
