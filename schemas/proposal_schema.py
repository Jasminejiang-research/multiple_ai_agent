"""Pydantic schemas for investor-style business proposals."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class PainPoint(BaseModel):
    """A specific problem or unmet need in the target market."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[
        str,
        Field(
            min_length=3,
            max_length=120,
            description="Short headline for this pain point (e.g. 'Manual invoice reconciliation').",
        ),
    ]
    description: Annotated[
        str,
        Field(
            min_length=20,
            description=(
                "Detailed explanation of the problem: who experiences it, how often, "
                "and what negative impact it causes (cost, time, risk, frustration)."
            ),
        ),
    ]
    severity: Annotated[
        str,
        Field(
            description=(
                "Qualitative severity rating: 'low', 'medium', or 'high'. "
                "Reflects urgency and willingness to pay for a solution."
            ),
            pattern=r"^(low|medium|high)$",
        ),
    ]


class TargetAudience(BaseModel):
    """Primary customer segment the proposal is designed to serve."""

    model_config = ConfigDict(str_strip_whitespace=True)

    segment_name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            description="Name of the customer segment (e.g. 'SMB e-commerce retailers').",
        ),
    ]
    demographics: Annotated[
        str,
        Field(
            min_length=10,
            description=(
                "Key demographic or firmographic traits: company size, industry, geography, "
                "role/title of the buyer, or income bracket as relevant."
            ),
        ),
    ]
    needs: Annotated[
        str,
        Field(
            min_length=10,
            description="Primary needs, jobs-to-be-done, or goals this segment is trying to achieve.",
        ),
    ]
    estimated_size: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Estimated number of potential customers or accounts in this segment "
                "(e.g. '2.5M SMBs in North America')."
            ),
        ),
    ]


class MarketSize(BaseModel):
    """Top-down market sizing using the TAM / SAM / SOM framework."""

    model_config = ConfigDict(str_strip_whitespace=True)

    tam: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Total Addressable Market: the full revenue opportunity if 100% of the "
                "theoretical market were captured. Include currency and time horizon."
            ),
        ),
    ]
    sam: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Serviceable Addressable Market: the portion of TAM reachable with the "
                "proposed product, geography, and business model."
            ),
        ),
    ]
    som: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Serviceable Obtainable Market: realistic near-term capture "
                "(typically 3–5 years) given competition and go-to-market capacity."
            ),
        ),
    ]
    growth_rate: Annotated[
        str,
        Field(
            min_length=3,
            description=(
                "Expected annual market growth rate with brief justification "
                "(e.g. '12% CAGR driven by digital adoption')."
            ),
        ),
    ]


class FinancialAssumptions(BaseModel):
    """Core financial assumptions investors use to evaluate viability."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pricing_model: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "How revenue is generated: subscription tiers, transaction fees, "
                "licensing, freemium, etc. Include indicative price points."
            ),
        ),
    ]
    average_revenue_per_customer: Annotated[
        str,
        Field(
            min_length=3,
            description=(
                "Expected annual or monthly revenue per customer/account (ARPU/ACV). "
                "State the time period explicitly."
            ),
        ),
    ]
    gross_margin: Annotated[
        str,
        Field(
            min_length=3,
            description=(
                "Estimated gross margin percentage after direct costs "
                "(COGS, hosting, payment processing, support)."
            ),
        ),
    ]
    customer_acquisition_cost: Annotated[
        str,
        Field(
            min_length=3,
            description=(
                "Estimated cost to acquire one paying customer (CAC), "
                "including marketing and sales expenses."
            ),
        ),
    ]
    monthly_burn_rate: Annotated[
        str,
        Field(
            min_length=3,
            description=(
                "Projected monthly cash burn during the growth phase "
                "(payroll, infrastructure, marketing, overhead)."
            ),
        ),
    ]
    runway_months: Annotated[
        int,
        Field(
            ge=1,
            le=120,
            description=(
                "Number of months the business can operate at the projected burn rate "
                "before additional funding is required."
            ),
        ),
    ]
    break_even_timeline: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Estimated time to reach profitability or cash-flow break-even "
                "(e.g. 'Month 18 at 500 paying customers')."
            ),
        ),
    ]


class CompetitiveAdvantage(BaseModel):
    """A defensible differentiator versus existing alternatives."""

    model_config = ConfigDict(str_strip_whitespace=True)

    advantage: Annotated[
        str,
        Field(
            min_length=5,
            max_length=150,
            description="Concise statement of the competitive edge (e.g. proprietary data, speed, cost).",
        ),
    ]
    description: Annotated[
        str,
        Field(
            min_length=10,
            description="Why this advantage is hard to replicate and how it benefits customers.",
        ),
    ]


class BusinessProposal(BaseModel):
    """
    Structured investor-style business proposal.

    Designed for strict LLM output validation in Phase 1 of the Open Proposal Agent.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    project_name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            description="Official name of the venture or product being proposed.",
        ),
    ]
    tagline: Annotated[
        str,
        Field(
            min_length=5,
            max_length=200,
            description="One-line value proposition that captures the essence of the offering.",
        ),
    ]
    executive_summary: Annotated[
        str,
        Field(
            min_length=50,
            description=(
                "High-level overview (2–4 paragraphs) covering the opportunity, solution, "
                "market, traction or readiness, and funding ask."
            ),
        ),
    ]
    pain_points: Annotated[
        list[PainPoint],
        Field(
            min_length=1,
            max_length=5,
            description="List of 1–5 core problems the target market faces that this proposal addresses.",
        ),
    ]
    solution: Annotated[
        str,
        Field(
            min_length=30,
            description=(
                "Detailed description of the product or service: what it does, "
                "how it works, and how it resolves the stated pain points."
            ),
        ),
    ]
    unique_value_proposition: Annotated[
        str,
        Field(
            min_length=20,
            description=(
                "Clear statement of what makes this solution meaningfully different "
                "and better than status-quo alternatives."
            ),
        ),
    ]
    target_audiences: Annotated[
        list[TargetAudience],
        Field(
            min_length=1,
            max_length=4,
            description="Primary customer segments, ordered by priority (most important first).",
        ),
    ]
    market_size: Annotated[
        MarketSize,
        Field(description="TAM / SAM / SOM market sizing with growth context."),
    ]
    business_model: Annotated[
        str,
        Field(
            min_length=20,
            description=(
                "How the company creates, delivers, and captures value: "
                "revenue streams, unit economics logic, and key partnerships."
            ),
        ),
    ]
    competitive_landscape: Annotated[
        str,
        Field(
            min_length=20,
            description=(
                "Overview of direct and indirect competitors, substitutes, "
                "and the current market gap this proposal fills."
            ),
        ),
    ]
    competitive_advantages: Annotated[
        list[CompetitiveAdvantage],
        Field(
            min_length=1,
            max_length=5,
            description="1–5 defensible differentiators that support long-term market position.",
        ),
    ]
    go_to_market_strategy: Annotated[
        str,
        Field(
            min_length=20,
            description=(
                "Plan for reaching and converting customers: channels, partnerships, "
                "pricing launch strategy, and early traction milestones."
            ),
        ),
    ]
    financial_assumptions: Annotated[
        FinancialAssumptions,
        Field(description="Baseline financial assumptions for investor evaluation."),
    ]
    funding_ask: Annotated[
        str,
        Field(
            min_length=5,
            description=(
                "Amount of capital being raised (currency and round type) "
                "and high-level allocation across product, team, and GTM."
            ),
        ),
    ]
    key_metrics: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=8,
            description=(
                "2–8 KPIs the venture will track (e.g. MRR, churn, LTV:CAC, NPS). "
                "Each item should be a concise metric name with optional target."
            ),
        ),
    ]
    risks_and_mitigations: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=6,
            description=(
                "Key risks paired with mitigation strategies. "
                "Each item should state the risk and proposed countermeasure."
            ),
        ),
    ]
