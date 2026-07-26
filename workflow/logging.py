"""Workflow run logging helpers for the deterministic proposal graph."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, TypeAlias

from pydantic import BaseModel
from sqlalchemy.orm import Session

from storage.repositories import (
    add_run_token_usage,
    save_agent_output,
    save_error,
    save_node_output,
    update_run_status,
)
from workflow.llm_client import capture_llm_usage
from workflow.state import WorkflowState

WORKFLOW_VERSION = "workflow-v1"
PROMPT_VERSION = "phase2-prompts-v1"
MULTI_AGENT_VERSION = "multi-agent-rag-v1"
MULTI_AGENT_PROMPT_VERSION = "phase4-rag-agent-prompts-v1"
WORKFLOW_STEP_NAMES: tuple[str, ...] = (
    "input_validator",
    "proposal_planner",
    "section_writer",
    "proposal_assembler",
    "basic_critic",
    "revision",
    "export",
)
MULTI_AGENT_STEP_NAMES: tuple[str, ...] = (
    "input_validator",
    "supervisor",
    "research",
    "strategy",
    "finance",
    "rag_retrieval",
    "writer",
    "critic",
    "revision",
    "export",
)
LLM_PROMPT_VERSION_BY_STEP: dict[str, str] = {
    "proposal_planner": PROMPT_VERSION,
    "section_writer": PROMPT_VERSION,
    "basic_critic": PROMPT_VERSION,
    "revision": PROMPT_VERSION,
    "supervisor": MULTI_AGENT_PROMPT_VERSION,
    "research": MULTI_AGENT_PROMPT_VERSION,
    "strategy": MULTI_AGENT_PROMPT_VERSION,
    "finance": MULTI_AGENT_PROMPT_VERSION,
    "writer": MULTI_AGENT_PROMPT_VERSION,
    "critic": MULTI_AGENT_PROMPT_VERSION,
}

SessionFactory: TypeAlias = Callable[[], AbstractContextManager[Session]]
WorkflowNode: TypeAlias = Callable[[WorkflowState], WorkflowState]


def serialize_for_log(value: Any) -> Any:
    """Convert workflow values into JSON-safe snapshots for SQLite JSON columns."""
    if isinstance(value, BaseModel):
        return serialize_for_log(value.model_dump())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): serialize_for_log(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_for_log(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def with_workflow_logging(
    step_name: str,
    node: WorkflowNode,
    session_factory: SessionFactory | None,
) -> WorkflowNode:
    """Wrap a workflow node with start, completion, and error persistence."""

    def logged_node(state: WorkflowState) -> WorkflowState:
        run_id = state.get("run_id")
        if session_factory is None or not run_id:
            return node(state)

        input_snapshot = serialize_for_log(state)
        prompt_version = LLM_PROMPT_VERSION_BY_STEP.get(step_name)
        start_snapshot: dict[str, Any] = {"status": "started"}
        if prompt_version:
            start_snapshot["prompt_version"] = prompt_version

        with session_factory() as session:
            save_node_output(
                session,
                run_id=run_id,
                node_name=step_name,
                input_snapshot=input_snapshot,
                output_snapshot=start_snapshot,
            )
            session.commit()

        usage_tracker = None
        try:
            with capture_llm_usage() as usage_tracker:
                output = node(state)
        except Exception as exc:
            token_usage = (
                usage_tracker.as_dict()
                if usage_tracker is not None
                else None
            )
            with session_factory() as session:
                save_node_output(
                    session,
                    run_id=run_id,
                    node_name=step_name,
                    input_snapshot=input_snapshot,
                    output_snapshot={
                        "status": "failed",
                        "error_type": type(exc).__name__,
                    },
                    token_usage=token_usage,
                )
                if token_usage is not None:
                    add_run_token_usage(session, run_id, token_usage)
                save_error(
                    session,
                    run_id=run_id,
                    step_name=step_name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    stack_trace=traceback.format_exc(),
                )
                update_run_status(session, run_id, "failed")
                session.commit()
            raise

        token_usage = usage_tracker.as_dict()
        completed_snapshot: dict[str, Any] = {
            "status": "completed",
            "output": serialize_for_log(output),
        }
        if prompt_version:
            completed_snapshot["prompt_version"] = prompt_version

        with session_factory() as session:
            save_node_output(
                session,
                run_id=run_id,
                node_name=step_name,
                input_snapshot=input_snapshot,
                output_snapshot=completed_snapshot,
                token_usage=token_usage,
            )
            add_run_token_usage(session, run_id, token_usage)
            session.commit()

        return output

    return logged_node


def with_agent_output_persistence(
    node: WorkflowNode,
    *,
    agent_name: str,
    output_type: str,
    output_field: str,
    session_factory: SessionFactory | None,
) -> WorkflowNode:
    """Wrap an agent node and persist its validated state output."""

    def persisted_node(state: WorkflowState) -> WorkflowState:
        output = node(state)
        run_id = state.get("run_id")
        payload = output.get(output_field)
        if session_factory is not None and run_id and isinstance(payload, dict):
            with session_factory() as session:
                save_agent_output(
                    session,
                    run_id=run_id,
                    agent_name=agent_name,
                    output_type=output_type,
                    output_payload=serialize_for_log(payload),
                )
                session.commit()
        return output

    return persisted_node


def step_names_for_workflow(workflow_version: str | None) -> tuple[str, ...]:
    """Return the display order for a persisted workflow version."""
    if workflow_version == MULTI_AGENT_VERSION:
        return MULTI_AGENT_STEP_NAMES
    return WORKFLOW_STEP_NAMES


def summarize_step_statuses(run: Any) -> list[dict[str, str]]:
    """Return latest logged status for each workflow step in graph order."""
    latest_by_step: dict[str, dict[str, str]] = {}
    for node_output in sorted(
        run.node_outputs,
        key=lambda item: (item.created_at, item.id),
    ):
        snapshot = node_output.output_snapshot or {}
        status = str(snapshot.get("status", "completed"))
        latest_by_step[node_output.node_name] = {
            "step": node_output.node_name,
            "status": status,
            "prompt_version": str(snapshot.get("prompt_version", "")),
        }

    step_names = step_names_for_workflow(getattr(run, "workflow_version", None))
    return [
        latest_by_step[step_name]
        for step_name in step_names
        if step_name in latest_by_step
    ]
