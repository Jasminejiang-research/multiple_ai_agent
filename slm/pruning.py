"""Schema and prompt pruning for the SLM arm.

Qwen2.5-7B degenerates into repetition loops on long structured outputs: every
live run against the full agent schemas ended in ``finish_reason='length'``
with the tail full of repeated punctuation or whitespace. Pruning attacks the
cause instead of the symptom: the model is asked for a *slim* schema -- only
the analytical core, with short lists -- and the adapter deterministically
expands that output into the full strict schema (optional fields take their
schema defaults; the only synthesized values are fixed boilerplate, documented
per expander).

This deliberately trades absolute comparability with the Gemini arm (which
fills the full schemas) for a pipeline the 7B model can actually complete.
Phase 7 must treat the SLM arm as *relatively* comparable only; the pruned
fields are listed in slm/README.md.

Prompt pruning follows the same logic: the agent prompt's ``# Output Schema``
section (a full-schema JSON example that contradicts the slim schema) and the
``# Quality Criteria`` section are removed -- together roughly half the prompt.
The slim schema appended by ``SLMClient`` becomes the single source of truth.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
)

# The boilerplate FinanceAssumptions.assumption_notice demands. This exact
# sentence appears in prompts/finance_agent.md as the canonical example; the
# model's own attempts at it failed the assumption-not-forecast validator twice
# in live runs, so it is supplied deterministically rather than generated.
ASSUMPTION_NOTICE = (
    "All financial figures are assumptions for planning discussion, "
    "not forecasts."
)

_PRUNED_PROMPT_SECTIONS = ("# Output Schema", "# Quality Criteria")

_BREVITY_DIRECTIVE = (
    "# Output Brevity (SLM)\n\n"
    "Keep every string to 1-3 concise sentences. Never pad, repeat a phrase, "
    "or fill space with punctuation or whitespace. Stop as soon as the JSON "
    "object is complete."
)


def condense_prompt(prompt: str) -> str:
    """Drop the full-schema example and quality-criteria sections.

    The slim schema appended by the client is authoritative; leaving the
    original ``# Output Schema`` block in place would show the model the full
    shape and invite it to produce exactly the output being pruned away.
    """
    condensed = prompt
    for heading in _PRUNED_PROMPT_SECTIONS:
        # From the heading to the next top-level heading (or end of text).
        condensed = re.sub(
            rf"^{re.escape(heading)}\n.*?(?=^# |\Z)",
            "",
            condensed,
            flags=re.MULTILINE | re.DOTALL,
        )
    return f"{condensed.rstrip()}\n\n{_BREVITY_DIRECTIVE}"


class SlimResearchFinding(BaseModel):
    """Analytical core of ``ResearchFinding``: what, and why it holds."""

    model_config = ConfigDict(str_strip_whitespace=True)

    topic: Annotated[str, Field(min_length=3, max_length=80)]
    finding: Annotated[str, Field(min_length=20, max_length=400)]
    rationale: Annotated[str, Field(min_length=20, max_length=400)]


class SlimResearchAnalysis(BaseModel):
    """ResearchAnalysis without confidence labels and review bookkeeping."""

    model_config = ConfigDict(str_strip_whitespace=True)

    analysis_summary: Annotated[str, Field(min_length=20, max_length=600)]
    market_trends: Annotated[
        list[SlimResearchFinding], Field(min_length=1, max_length=3)
    ]
    customer_notes: Annotated[
        list[SlimResearchFinding], Field(min_length=1, max_length=3)
    ]
    competitor_assumptions: Annotated[
        list[SlimResearchFinding], Field(min_length=1, max_length=3)
    ]


class SlimStrategyInsight(BaseModel):
    """Analytical core of ``StrategyInsight``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    topic: Annotated[str, Field(min_length=3, max_length=80)]
    recommendation: Annotated[str, Field(min_length=20, max_length=400)]
    rationale: Annotated[str, Field(min_length=20, max_length=400)]


class SlimStrategyAnalysis(BaseModel):
    """StrategyAnalysis reduced to its four insight lists."""

    model_config = ConfigDict(str_strip_whitespace=True)

    analysis_summary: Annotated[str, Field(min_length=20, max_length=600)]
    value_proposition: Annotated[
        list[SlimStrategyInsight], Field(min_length=1, max_length=3)
    ]
    business_model_logic: Annotated[
        list[SlimStrategyInsight], Field(min_length=1, max_length=3)
    ]
    gtm_strategy: Annotated[
        list[SlimStrategyInsight], Field(min_length=1, max_length=3)
    ]
    moat_hypotheses: Annotated[
        list[SlimStrategyInsight], Field(min_length=1, max_length=3)
    ]


class SlimFinanceAssumption(BaseModel):
    """Analytical core of ``FinanceAssumption``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    topic: Annotated[str, Field(min_length=3, max_length=80)]
    assumption: Annotated[str, Field(min_length=20, max_length=400)]
    rationale: Annotated[str, Field(min_length=20, max_length=400)]


class SlimFinanceAssumptions(BaseModel):
    """FinanceAssumptions without the boilerplate notice and bookkeeping."""

    model_config = ConfigDict(str_strip_whitespace=True)

    analysis_summary: Annotated[str, Field(min_length=20, max_length=600)]
    revenue_assumptions: Annotated[
        list[SlimFinanceAssumption], Field(min_length=1, max_length=3)
    ]
    cost_assumptions: Annotated[
        list[SlimFinanceAssumption], Field(min_length=1, max_length=3)
    ]
    unit_economics_assumptions: Annotated[
        list[SlimFinanceAssumption], Field(min_length=1, max_length=3)
    ]
    break_even_discussion: Annotated[
        str, Field(min_length=30, max_length=600)
    ]


class SlimProposalSection(BaseModel):
    """A proposal section reduced to its narrative content.

    ``key_claims``, ``source_ids``, and ``confidence`` are dropped; they take
    their schema defaults on expansion, which also makes the citation checks
    trivially pass. That is the single largest comparability concession of the
    pruned arm and is called out in slm/README.md.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=2, max_length=60)]
    content: Annotated[str, Field(min_length=40, max_length=2400)]


def expand_research(slim: SlimResearchAnalysis) -> ResearchAnalysis:
    """Expand a slim research packet; nothing is synthesized."""
    return ResearchAnalysis.model_validate(
        {
            "analysis_summary": slim.analysis_summary,
            "market_trends": [f.model_dump() for f in slim.market_trends],
            "customer_notes": [f.model_dump() for f in slim.customer_notes],
            "competitor_assumptions": [
                f.model_dump() for f in slim.competitor_assumptions
            ],
        }
    )


def expand_strategy(slim: SlimStrategyAnalysis) -> StrategyAnalysis:
    """Expand a slim strategy packet; nothing is synthesized."""
    return StrategyAnalysis.model_validate(
        {
            "analysis_summary": slim.analysis_summary,
            "value_proposition": [
                i.model_dump() for i in slim.value_proposition
            ],
            "business_model_logic": [
                i.model_dump() for i in slim.business_model_logic
            ],
            "gtm_strategy": [i.model_dump() for i in slim.gtm_strategy],
            "moat_hypotheses": [i.model_dump() for i in slim.moat_hypotheses],
        }
    )


def expand_finance(slim: SlimFinanceAssumptions) -> FinanceAssumptions:
    """Expand a slim finance packet.

    Synthesized: ``assumption_notice`` only -- fixed boilerplate whose exact
    wording the schema validator requires and live 7B runs failed to produce.
    """
    return FinanceAssumptions.model_validate(
        {
            "analysis_summary": slim.analysis_summary,
            "revenue_assumptions": [
                a.model_dump() for a in slim.revenue_assumptions
            ],
            "cost_assumptions": [
                a.model_dump() for a in slim.cost_assumptions
            ],
            "unit_economics_assumptions": [
                a.model_dump() for a in slim.unit_economics_assumptions
            ],
            "break_even_discussion": slim.break_even_discussion,
            "assumption_notice": ASSUMPTION_NOTICE,
        }
    )


PRUNED_SPECS: dict[str, tuple[type[BaseModel], type[BaseModel], object]] = {
    "research": (ResearchAnalysis, SlimResearchAnalysis, expand_research),
    "strategy": (StrategyAnalysis, SlimStrategyAnalysis, expand_strategy),
    "finance": (FinanceAssumptions, SlimFinanceAssumptions, expand_finance),
}


__all__ = [
    "ASSUMPTION_NOTICE",
    "PRUNED_SPECS",
    "SlimFinanceAssumptions",
    "SlimProposalSection",
    "SlimResearchAnalysis",
    "SlimStrategyAnalysis",
    "condense_prompt",
    "expand_finance",
    "expand_research",
    "expand_strategy",
]
