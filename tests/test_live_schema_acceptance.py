"""Cheap live checks that Gemini accepts every production response schema."""

from __future__ import annotations

import os

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
    ProposalDraft,
    ProposalOutline,
    RevisedProposal,
    RevisedProposalPatch,
    SectionDrafts,
)
from workflow.gemini_schema import relaxed_response_schema
from workflow.llm_client import DEFAULT_MODEL_NAME

# This mirrors the production schema inventory guarded offline by T2.
# SupervisorPlan is excluded because supervisor_agent_node builds it
# deterministically without an LLM request.
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
    """Fail only when Gemini rejects a schema before generation starts."""
    try:
        gemini_client.models.generate_content(
            model=os.getenv("DEFAULT_MODEL", DEFAULT_MODEL_NAME),
            contents="Return one minimal JSON object.",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=relaxed_response_schema(model),
                temperature=0.0,
                max_output_tokens=16,
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
