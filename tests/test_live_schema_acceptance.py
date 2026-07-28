"""Cheap live checks that Gemini accepts every production response schema."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)
from schemas.proposal_schema import BusinessProposal
from schemas.workflow import (
    CritiqueReport,
    ProposalOutline,
    RevisedProposalPatch,
    SectionDrafts,
)
from workflow.generation_batches import (
    PROPOSAL_DRAFT_BATCH_MODELS,
    REVISED_PROPOSAL_BATCH_MODELS,
)
from workflow.gemini_schema import relaxed_response_schema
from workflow.llm_client import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL_NAME

# This mirrors the production schema inventory guarded offline by T2.
# SupervisorPlan is excluded because supervisor_agent_node builds it
# deterministically without an LLM request.
GENERATION_SCHEMAS = (
    BusinessProposal,
    ProposalOutline,
    SectionDrafts,
    CritiqueReport,
    RevisedProposalPatch,
    ResearchAnalysis,
    StrategyAnalysis,
    FinanceAssumptions,
    *PROPOSAL_DRAFT_BATCH_MODELS,
    *REVISED_PROPOSAL_BATCH_MODELS,
)


def _minimal_complete_value(schema: dict[str, Any]) -> Any:
    """Build a tiny value that traverses every property and array-item schema."""
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        for option in any_of:
            if isinstance(option, dict) and option.get("type") != "null":
                return _minimal_complete_value(option)
        return None

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next(
            (value for value in schema_type if value != "null"),
            "null",
        )
    if schema_type == "object":
        properties = schema.get("properties", {})
        return {
            property_name: _minimal_complete_value(property_schema)
            for property_name, property_schema in properties.items()
        }
    if schema_type == "array":
        return [_minimal_complete_value(schema.get("items", {}))]
    if schema_type == "boolean":
        return False
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "null":
        return None
    return "x"


def _assert_complete_shape(actual: Any, expected: Any, path: str = "$") -> None:
    """Assert that Gemini traversed every object property and array item."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path} must be an object"
        missing = set(expected) - set(actual)
        assert not missing, f"{path} omitted properties: {sorted(missing)}"
        for key, expected_value in expected.items():
            _assert_complete_shape(actual[key], expected_value, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path} must be an array"
        assert actual, f"{path} must include one item to exercise its item schema"
        _assert_complete_shape(actual[0], expected[0], f"{path}[0]")


@pytest.fixture(scope="module")
def gemini_client():
    """Create one live client or skip when credentials are unavailable."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not set; skipping live schema acceptance.")
    return genai.Client(api_key=api_key)


@pytest.mark.live
@pytest.mark.parametrize(
    "model",
    GENERATION_SCHEMAS,
    ids=lambda model: model.__name__,
)
def test_gemini_accepts_generation_schema(gemini_client, model: type) -> None:
    """Generate and verify a minimal object that traverses the complete schema."""
    generation_schema = relaxed_response_schema(model)
    minimal_value = _minimal_complete_value(generation_schema)
    prompt = (
        "Return exactly this minimal JSON value, including every object "
        "property and the single item in every array. Return JSON only:\n"
        f"{json.dumps(minimal_value, separators=(',', ':'))}"
    )
    try:
        response = gemini_client.models.generate_content(
            model=os.getenv("DEFAULT_MODEL", DEFAULT_MODEL_NAME),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=generation_schema,
                temperature=0.0,
                max_output_tokens=int(
                    os.getenv(
                        "LLM_MAX_OUTPUT_TOKENS_PER_REQUEST",
                        DEFAULT_MAX_OUTPUT_TOKENS,
                    )
                ),
            ),
        )
    except Exception as exc:
        message = str(exc)
        normalized_message = message.lower()
        status_code = getattr(exc, "code", None)
        if (
            status_code == 400
            or "invalid_argument" in normalized_message
            or "too many states" in normalized_message
        ):
            pytest.fail(
                f"Gemini rejected {model.__name__} generation schema: {message}",
                pytrace=False,
            )
        if status_code == 429:
            pytest.skip(
                f"Gemini quota exhausted while checking {model.__name__}; "
                "schema acceptance is unknown."
            )
        if status_code is not None and status_code >= 500:
            pytest.skip(
                f"Transient Gemini error {status_code} while checking "
                f"{model.__name__}; retry later."
            )
        raise

    assert response.text, f"Gemini returned empty text for {model.__name__}"
    try:
        actual_value = json.loads(response.text)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"Gemini returned incomplete JSON for {model.__name__}: {exc}",
            pytrace=False,
        )
    _assert_complete_shape(actual_value, minimal_value)
