"""Default LLM adapter factories for deterministic workflow nodes.

Every factory returns a thin ``StructuredJsonLLM`` bound to one output schema.
No Gemini client or config is created here; that is the exclusive job of
``workflow.llm_client.LLMClient``.
"""

from __future__ import annotations

from schemas.workflow import CritiqueReport, ProposalOutline, RevisedProposal, SectionDrafts
from workflow.llm_client import (
    DEFAULT_MODEL_NAME,
    StructuredJsonLLM,
    create_default_llm_client,
)

MODEL_NAME = DEFAULT_MODEL_NAME


def create_default_planner_llm() -> StructuredJsonLLM:
    """Create the default production LLM adapter for the planner node."""
    return StructuredJsonLLM(
        create_default_llm_client(), ProposalOutline, temperature=0.2
    )


def create_default_section_writer_llm() -> StructuredJsonLLM:
    """Create the default production LLM adapter for the SectionWriter node."""
    return StructuredJsonLLM(
        create_default_llm_client(), SectionDrafts, temperature=0.3
    )


def create_default_basic_critic_llm() -> StructuredJsonLLM:
    """Create the default production LLM adapter for the BasicCritic node."""
    return StructuredJsonLLM(
        create_default_llm_client(), CritiqueReport, temperature=0.2
    )


def create_default_revision_llm() -> StructuredJsonLLM:
    """Create the default production LLM adapter for the RevisionNode."""
    return StructuredJsonLLM(
        create_default_llm_client(), RevisedProposal, temperature=0.2
    )
