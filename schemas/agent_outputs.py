"""Pydantic schemas for controlled multi-agent outputs."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentRole = Literal["research", "strategy", "finance", "writer", "critic"]
ResearchConfidence = Literal["high", "medium", "low"]


class SupervisorTask(BaseModel):
    """One task assigned by the Supervisor to a downstream agent.

    The task describes what another agent should analyze or produce. It must not
    contain the final research, strategy, finance, writing, or critique result.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: Annotated[
        str,
        Field(
            min_length=3,
            max_length=40,
            pattern=r"^[a-z][a-z0-9_]*$",
            description="Stable snake_case identifier for this supervised task.",
        ),
    ]
    agent_role: Annotated[
        AgentRole,
        Field(description="Downstream agent responsible for this task."),
    ]
    objective: Annotated[
        str,
        Field(
            min_length=20,
            description="What the assigned agent should accomplish.",
        ),
    ]
    input_requirements: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=8,
            description="Brief-supported inputs or prior outputs this task needs.",
        ),
    ]
    expected_output: Annotated[
        str,
        Field(
            min_length=10,
            description="Structured artifact expected from the assigned agent.",
        ),
    ]
    depends_on: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=5,
            description="Task IDs that must finish before this task can run.",
        ),
    ]


class SupervisorPlan(BaseModel):
    """Structured routing plan produced by the Supervisor Agent."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    plan_summary: Annotated[
        str,
        Field(
            min_length=20,
            description="Short explanation of how work will be split across agents.",
        ),
    ]
    tasks: Annotated[
        list[SupervisorTask],
        Field(
            min_length=1,
            max_length=8,
            description="Ordered task plan for selected downstream agents.",
        ),
    ]
    selected_agents: Annotated[
        list[AgentRole],
        Field(
            min_length=1,
            max_length=5,
            description="Agent roles the Supervisor decided should be called.",
        ),
    ]
    skipped_agents: Annotated[
        list[AgentRole],
        Field(
            default_factory=list,
            max_length=5,
            description="Agent roles intentionally skipped for this run.",
        ),
    ]
    needs_human_review: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Uncertainties the user should confirm before or during execution.",
        ),
    ]

    @model_validator(mode="after")
    def ensure_routing_matches_tasks(self) -> "SupervisorPlan":
        """Require selected agents and dependencies to match the planned tasks."""
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("SupervisorPlan.tasks must use unique task_id values.")

        planned_roles = {task.agent_role for task in self.tasks}
        selected_roles = set(self.selected_agents)
        if planned_roles != selected_roles:
            raise ValueError("SupervisorPlan.selected_agents must match task agent roles.")

        skipped_roles = set(self.skipped_agents)
        if selected_roles & skipped_roles:
            raise ValueError("SupervisorPlan cannot both select and skip the same agent.")

        known_task_ids = set(task_ids)
        for task in self.tasks:
            unknown_dependencies = set(task.depends_on) - known_task_ids
            if unknown_dependencies:
                raise ValueError(
                    "SupervisorTask.depends_on must reference existing task_id values."
                )

        return self


class ResearchFinding(BaseModel):
    """One brief-grounded research observation for downstream proposal agents."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    topic: Annotated[
        str,
        Field(
            min_length=3,
            max_length=120,
            description="Short topic label for the research finding.",
        ),
    ]
    finding: Annotated[
        str,
        Field(
            min_length=20,
            description="Research note written as an assumption or hypothesis, not a verified fact.",
        ),
    ]
    rationale: Annotated[
        str,
        Field(
            min_length=20,
            description="Why this finding follows from the user brief or known inputs.",
        ),
    ]
    confidence: Annotated[
        ResearchConfidence,
        Field(description="Confidence level based on evidence available to this agent."),
    ] = "medium"


class UnsupportedClaim(BaseModel):
    """A claim that needs evidence before it can be used as a proposal fact."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    claim: Annotated[
        str,
        Field(
            min_length=10,
            description="The unsupported claim or tempting market statement.",
        ),
    ]
    why_unsupported: Annotated[
        str,
        Field(
            min_length=20,
            description="Explanation of what evidence is missing.",
        ),
    ]
    needed_evidence: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=5,
            description="Source types or facts needed before the claim can be trusted.",
        ),
    ]


class ResearchAnalysis(BaseModel):
    """Structured output from the Research Agent.

    The Research Agent summarizes market, customer, and competitor hypotheses for
    later agents. It does not write proposal prose or present unsupported facts
    as verified conclusions.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    analysis_summary: Annotated[
        str,
        Field(
            min_length=20,
            description="Brief overview of the research analysis and uncertainty level.",
        ),
    ]
    market_trends: Annotated[
        list[ResearchFinding],
        Field(
            min_length=1,
            max_length=6,
            description="Market trend hypotheses relevant to the brief.",
        ),
    ]
    customer_notes: Annotated[
        list[ResearchFinding],
        Field(
            min_length=1,
            max_length=6,
            description="Customer pain, behavior, and buying-context notes.",
        ),
    ]
    competitor_assumptions: Annotated[
        list[ResearchFinding],
        Field(
            min_length=1,
            max_length=6,
            description="Competitor or substitute assumptions that require later evidence.",
        ),
    ]
    unsupported_claims: Annotated[
        list[UnsupportedClaim],
        Field(
            default_factory=list,
            max_length=8,
            description="Claims that must not be treated as verified without sources.",
        ),
    ]
    needs_human_review: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Questions or assumptions a user should confirm.",
        ),
    ]


class StrategyInsight(BaseModel):
    """One strategy recommendation grounded in the brief or prior analysis."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    topic: Annotated[
        str,
        Field(
            min_length=3,
            max_length=120,
            description="Short topic label for this strategy insight.",
        ),
    ]
    recommendation: Annotated[
        str,
        Field(
            min_length=20,
            description="Strategic recommendation written without unsupported market data.",
        ),
    ]
    rationale: Annotated[
        str,
        Field(
            min_length=20,
            description="Why this recommendation follows from the available input.",
        ),
    ]
    confidence: Annotated[
        ResearchConfidence,
        Field(description="Confidence level based on the available brief and analysis packets."),
    ] = "medium"


class StrategyAnalysis(BaseModel):
    """Structured output from the Strategy Agent.

    The Strategy Agent designs positioning, business model logic, GTM strategy,
    and moat hypotheses. It does not invent market data or write proposal prose.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    analysis_summary: Annotated[
        str,
        Field(
            min_length=20,
            description="Brief overview of the strategic direction and uncertainty level.",
        ),
    ]
    value_proposition: Annotated[
        list[StrategyInsight],
        Field(
            min_length=1,
            max_length=5,
            description="Customer-facing value proposition recommendations.",
        ),
    ]
    business_model_logic: Annotated[
        list[StrategyInsight],
        Field(
            min_length=1,
            max_length=5,
            description="How the product could create, deliver, and capture value.",
        ),
    ]
    gtm_strategy: Annotated[
        list[StrategyInsight],
        Field(
            min_length=1,
            max_length=5,
            description="Go-to-market motions and sequencing hypotheses.",
        ),
    ]
    moat_hypotheses: Annotated[
        list[StrategyInsight],
        Field(
            min_length=1,
            max_length=5,
            description="Defensibility hypotheses that require later validation.",
        ),
    ]
    unsupported_market_data: Annotated[
        list[UnsupportedClaim],
        Field(
            default_factory=list,
            max_length=8,
            description="Market-size or growth claims the strategy must not treat as facts.",
        ),
    ]
    needs_human_review: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Strategic assumptions a user should confirm.",
        ),
    ]


class FinanceAssumption(BaseModel):
    """One financial assumption clearly labeled as a hypothesis, not a forecast."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    topic: Annotated[
        str,
        Field(
            min_length=3,
            max_length=120,
            description="Short label for this financial assumption.",
        ),
    ]
    assumption: Annotated[
        str,
        Field(
            min_length=20,
            description="Financial assumption phrased as an assumption, not a prediction.",
        ),
    ]
    rationale: Annotated[
        str,
        Field(
            min_length=20,
            description="Why this assumption follows from the brief or strategy context.",
        ),
    ]
    confidence: Annotated[
        ResearchConfidence,
        Field(description="Confidence level based on the available brief and analysis packets."),
    ] = "medium"
    needs_validation: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=5,
            description="Evidence, user input, or calculations needed before relying on this assumption.",
        ),
    ]


class FinanceAssumptions(BaseModel):
    """Structured output from the Finance Agent.

    The Finance Agent frames revenue, cost, unit economics, and break-even
    assumptions. It must not present any numbers as accurate predictions.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    analysis_summary: Annotated[
        str,
        Field(
            min_length=20,
            description="Brief overview of the financial assumption set and uncertainty level.",
        ),
    ]
    revenue_assumptions: Annotated[
        list[FinanceAssumption],
        Field(
            min_length=1,
            max_length=6,
            description="Revenue model and monetization assumptions.",
        ),
    ]
    cost_assumptions: Annotated[
        list[FinanceAssumption],
        Field(
            min_length=1,
            max_length=6,
            description="Operating, delivery, acquisition, and fixed-cost assumptions.",
        ),
    ]
    unit_economics_assumptions: Annotated[
        list[FinanceAssumption],
        Field(
            min_length=1,
            max_length=6,
            description="Customer-level economics such as pricing, margin, CAC, payback, or retention assumptions.",
        ),
    ]
    break_even_discussion: Annotated[
        str,
        Field(
            min_length=30,
            description="Qualitative break-even discussion with assumptions labeled as uncertain.",
        ),
    ]
    assumption_notice: Annotated[
        str,
        Field(
            min_length=30,
            description="Explicit notice that all figures are assumptions, not forecasts.",
        ),
    ]
    unsupported_financial_claims: Annotated[
        list[UnsupportedClaim],
        Field(
            default_factory=list,
            max_length=8,
            description="Financial claims that need evidence, benchmarks, or user confirmation.",
        ),
    ]
    needs_human_review: Annotated[
        list[str],
        Field(
            default_factory=list,
            max_length=8,
            description="Financial assumptions a user should confirm before proposal export.",
        ),
    ]

    @model_validator(mode="after")
    def ensure_assumption_notice_is_explicit(self) -> "FinanceAssumptions":
        """Require the output to state that financial figures are assumptions."""
        notice = self.assumption_notice.lower()
        if "assumption" not in notice or "forecast" not in notice:
            raise ValueError(
                "FinanceAssumptions.assumption_notice must say figures are assumptions, not forecasts."
            )
        return self
