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

from schemas.workflow import CritiqueReport, ProposalOutline, RevisedProposal, SectionDrafts
from workflow.gemini_schema import (
    _CONSTRAINT_KEYS,
    _is_expensive_enum,
    relaxed_response_schema,
)

WORKFLOW_MODELS = (ProposalOutline, SectionDrafts, CritiqueReport, RevisedProposal)


def _iter_keys(node: Any):
    """Yield every dict key found anywhere in a nested schema fragment."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_keys(item)


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
    assert schema.get("properties"), f"{model.__name__} lost its properties"


@pytest.mark.parametrize("model", WORKFLOW_MODELS)
def test_relaxed_schema_drops_expensive_enums(model: type) -> None:
    """No large enum (the main serving-limit trigger) may survive relaxing."""
    schema = relaxed_response_schema(model)
    for enum_values in _iter_enums(schema):
        assert not _is_expensive_enum(enum_values), (
            f"{model.__name__} kept an expensive enum: {enum_values}"
        )


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
        pytest.fail(
            f"Gemini rejected the relaxed {model.__name__} schema: "
            f"{exc.code} {exc.message}"
        )

    assert response.text, f"Gemini returned empty text for {model.__name__}"
