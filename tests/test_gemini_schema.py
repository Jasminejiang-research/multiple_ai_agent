"""Regression tests for constraint-light Gemini generation schemas.

These guard against reintroducing the ``400 INVALID_ARGUMENT`` ("schema
produces a constraint that has too many states for serving") error that broke
the workflow run mode. The unit tests are offline and fast; the ``live`` test
optionally hits the real Gemini API and is skipped unless ``GEMINI_API_KEY``
is set.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
    SupervisorPlan,
)
from schemas.workflow import (
    CritiqueReport,
    ProposalDraft,
    ProposalOutline,
    RevisedProposal,
    SectionDrafts,
)
from workflow.gemini_schema import (
    _ANNOTATION_KEYS,
    _CONSTRAINT_KEYS,
    relaxed_response_schema,
)

# Every Pydantic model sent to Gemini as a response_schema, across the
# deterministic workflow (Phase 2) and the multi-agent mode (Phase 3). The
# Phase 3 models use ``extra="forbid"`` and therefore emit
# ``additionalProperties``, which Gemini rejects with a 400 unless stripped.
WORKFLOW_MODELS = (
    ProposalOutline,
    SectionDrafts,
    CritiqueReport,
    RevisedProposal,
    SupervisorPlan,
    ResearchAnalysis,
    StrategyAnalysis,
    FinanceAssumptions,
    ProposalDraft,
)


def _iter_keys(node: Any):
    """Yield every dict key found anywhere in a nested schema fragment."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_keys(item)


def _iter_schema_fragment_keys(node: Any):
    """Yield schema keywords without treating business property names as keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            if key == "properties" and isinstance(value, dict):
                for property_schema in value.values():
                    yield from _iter_schema_fragment_keys(property_schema)
            else:
                yield from _iter_schema_fragment_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_schema_fragment_keys(item)


def _iter_enums(node: Any):
    """Yield every ``enum`` value list found anywhere in a schema fragment."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "enum" and isinstance(value, list):
                yield value
            else:
                yield from _iter_enums(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_enums(item)


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_has_no_constraint_keys(model: type) -> None:
    """The relaxed schema must not contain any state-inflating constraints."""
    schema = relaxed_response_schema(model)
    keys = set(_iter_keys(schema))
    offending = keys & _CONSTRAINT_KEYS
    assert not offending, f"{model.__name__} leaked constraint keys: {sorted(offending)}"


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_has_no_additional_properties(model: type) -> None:
    """Regression: ``extra="forbid"`` models must not leak additionalProperties.

    Gemini rejects it with ``400 INVALID_ARGUMENT: Unknown name
    "additional_properties"``, which broke the Phase 3 multi-agent run mode.
    """
    keys = set(_iter_keys(relaxed_response_schema(model)))
    assert "additionalProperties" not in keys, (
        f"{model.__name__} leaked additionalProperties into the Gemini schema"
    )


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_inlines_all_refs(model: type) -> None:
    """The relaxed schema must inline ``$ref`` and drop the ``$defs`` block."""
    schema = relaxed_response_schema(model)
    keys = set(_iter_keys(schema))
    assert "$ref" not in keys, f"{model.__name__} still contains a $ref"
    assert "$defs" not in keys, f"{model.__name__} still contains a $defs block"


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_preserves_structure(model: type) -> None:
    """Stripping constraints must keep the object shape and its properties."""
    schema = relaxed_response_schema(model)
    assert schema.get("type") == "object"
    properties = schema.get("properties")
    assert properties, f"{model.__name__} lost its properties"
    assert set(properties) == set(model.model_json_schema().get("properties", {})), (
        f"{model.__name__} lost or changed a top-level business property"
    )


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_drops_all_enums(model: type) -> None:
    """No enum may survive because even small repeated enums inflate states."""
    assert not list(_iter_enums(relaxed_response_schema(model))), (
        f"{model.__name__} leaked an enum into the Gemini schema"
    )


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_drops_all_annotations(model: type) -> None:
    """Schema annotations add request text without defining JSON structure."""
    keys = set(_iter_schema_fragment_keys(relaxed_response_schema(model)))
    offending = keys & _ANNOTATION_KEYS
    assert not offending, f"{model.__name__} leaked annotations: {sorted(offending)}"


def test_relaxed_schema_preserves_title_business_property() -> None:
    """Annotation stripping must not delete a property whose name is ``title``."""
    schema = relaxed_response_schema(SectionDrafts)
    section_schema = schema["properties"]["sections"]["items"]
    assert "title" in section_schema["properties"]


@pytest.mark.live
@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_gemini_accepts_relaxed_schema(model: type) -> None:
    """Real Gemini must accept each relaxed schema without a 400 error.

    Skipped unless ``GEMINI_API_KEY`` is configured. This isolates the schema
    serving concern from output quality by using a trivial prompt.
    """
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set; skipping live Gemini schema check.")

    from google import genai
    from google.genai import errors, types

    from workflow.llm import MODEL_NAME

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=os.getenv("DEFAULT_MODEL", MODEL_NAME),
            contents="Return a minimal example object that satisfies the schema.",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=relaxed_response_schema(model),
                temperature=0.0,
            ),
        )
    except errors.ServerError as exc:
        pytest.skip(f"Transient Gemini server error ({exc.code}); retry later.")
    except errors.ClientError as exc:
        if exc.code == 429:
            pytest.skip("Gemini quota exhausted (429); schema was not rejected.")
        pytest.fail(
            f"Gemini rejected the relaxed {model.__name__} schema: "
            f"{exc.code} {exc.message}"
        )

    assert response.text, f"Gemini returned empty text for {model.__name__}"
