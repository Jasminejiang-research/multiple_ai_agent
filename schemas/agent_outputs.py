"""Pydantic schemas for controlled multi-agent outputs."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AgentRole = Literal["research", "strategy", "finance", "writer", "critic"]


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
