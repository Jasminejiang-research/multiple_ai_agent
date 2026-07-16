"""Tests for SQLAlchemy storage models."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

from storage.db import Base
from storage.models import (
    AgentOutput,
    ErrorRecord,
    NodeOutput,
    ProposalOutput,
    RunRecord,
)


def test_storage_models_create_expected_tables() -> None:
    """All run history tables should be creatable on SQLite."""
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {
        RunRecord.__tablename__,
        NodeOutput.__tablename__,
        AgentOutput.__tablename__,
        ProposalOutput.__tablename__,
        ErrorRecord.__tablename__,
    }.issubset(table_names)


def test_storage_models_include_core_audit_columns() -> None:
    """The models should cover the architecture's minimum run history fields."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    node_output_columns = {
        column["name"] for column in inspector.get_columns("node_outputs")
    }
    error_columns = {column["name"] for column in inspector.get_columns("error_records")}

    assert {
        "run_id",
        "status",
        "session_id",
        "workflow_version",
        "prompt_version",
        "model_name",
        "input_brief",
        "token_usage",
        "approximate_cost",
        "created_at",
        "updated_at",
    }.issubset(run_columns)
    assert {"node_name", "input_snapshot", "output_snapshot"}.issubset(
        node_output_columns
    )
    assert {"error_type", "error_message", "stack_trace"}.issubset(error_columns)
