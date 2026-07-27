"""SLM-backed adapter factories for existing workflow injection points."""

from __future__ import annotations

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
from workflow.llm_client import StructuredJsonLLM

from slm.client import SLMClient
from slm.config import SLMConfig


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
    return {
        name: StructuredJsonLLM(slm_client, schema, temperature=temperature)
        for name, (schema, temperature) in adapter_specs.items()
    }
