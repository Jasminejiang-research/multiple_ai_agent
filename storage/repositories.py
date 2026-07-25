"""Repository helpers for storing and reading proposal run history."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from schemas.source import SourceRecord
from storage.models import (
    AgentOutput,
    ErrorRecord,
    NodeOutput,
    RunRecord,
    SourceRecordModel,
    utc_now,
)


def create_run(
    session: Session,
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    workflow_version: str | None = None,
    prompt_version: str | None = None,
    model_name: str | None = None,
    input_brief: dict[str, Any] | None = None,
) -> RunRecord:
    """Create a run record and return the persisted SQLAlchemy model."""
    run = RunRecord(
        run_id=run_id or str(uuid4()),
        status="created",
        session_id=session_id,
        workflow_version=workflow_version,
        prompt_version=prompt_version,
        model_name=model_name,
        input_brief=input_brief,
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def update_run_status(session: Session, run_id: str, status: str) -> RunRecord:
    """Update a run status and return the updated run record."""
    run = get_run(session, run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    run.status = status
    run.updated_at = utc_now()
    session.flush()
    session.refresh(run)
    return run


def save_node_output(
    session: Session,
    *,
    run_id: str,
    node_name: str,
    input_snapshot: dict[str, Any] | None = None,
    output_snapshot: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
) -> NodeOutput:
    """Persist one workflow node input/output snapshot for a run."""
    _require_run(session, run_id)
    node_output = NodeOutput(
        run_id=run_id,
        node_name=node_name,
        input_snapshot=input_snapshot,
        output_snapshot=output_snapshot,
        token_usage=token_usage,
    )
    session.add(node_output)
    session.flush()
    session.refresh(node_output)
    return node_output


def save_agent_output(
    session: Session,
    *,
    run_id: str,
    agent_name: str,
    output_type: str | None,
    output_payload: dict[str, Any],
) -> AgentOutput:
    """Persist one schema-validated output produced by a named agent."""
    _require_run(session, run_id)
    agent_output = AgentOutput(
        run_id=run_id,
        agent_name=agent_name,
        output_type=output_type,
        output_payload=output_payload,
    )
    session.add(agent_output)
    session.flush()
    session.refresh(agent_output)
    return agent_output


def save_source_records(
    session: Session,
    *,
    run_id: str,
    sources: list[SourceRecord | dict[str, Any]],
) -> list[SourceRecordModel]:
    """Persist every controlled web-search result collected for one run."""
    _require_run(session, run_id)
    records: list[SourceRecordModel] = []
    for source_input in sources:
        source = SourceRecord.model_validate(source_input)
        record = SourceRecordModel(
            run_id=run_id,
            source_id=source.source_id,
            agent_name=source.agent_name,
            query=source.query,
            title=source.title,
            url=source.url,
            publisher=source.publisher,
            published_date=source.published_date,
            summary=source.summary,
            relevance_score=source.relevance_score,
            source_quality=source.source_quality.value,
            stale=source.stale,
            retrieved_at=source.retrieved_at,
        )
        session.add(record)
        records.append(record)
    session.flush()
    for record in records:
        session.refresh(record)
    return records


def save_error(
    session: Session,
    *,
    run_id: str,
    error_type: str,
    error_message: str,
    step_name: str | None = None,
    stack_trace: str | None = None,
) -> ErrorRecord:
    """Persist an error captured during a proposal generation run."""
    _require_run(session, run_id)
    error_record = ErrorRecord(
        run_id=run_id,
        step_name=step_name,
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
    )
    session.add(error_record)
    session.flush()
    session.refresh(error_record)
    return error_record


def get_run(session: Session, run_id: str) -> RunRecord | None:
    """Return a run and its basic child records by public run id."""
    statement = (
        select(RunRecord)
        .where(RunRecord.run_id == run_id)
        .options(
            selectinload(RunRecord.node_outputs),
            selectinload(RunRecord.agent_outputs),
            selectinload(RunRecord.errors),
            selectinload(RunRecord.sources),
        )
    )
    return session.scalar(statement)


def list_runs(session: Session, *, limit: int = 20) -> list[RunRecord]:
    """Return recent runs ordered from newest to oldest."""
    statement = (
        select(RunRecord)
        .order_by(RunRecord.created_at.desc(), RunRecord.id.desc())
        .limit(limit)
    )
    return list(session.scalars(statement))


def _require_run(session: Session, run_id: str) -> RunRecord:
    """Return a run or raise a readable error for invalid repository calls."""
    run = get_run(session, run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")
    return run
