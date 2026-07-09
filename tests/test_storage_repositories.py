"""Tests for repository helpers that persist run history."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.db import Base
from storage.repositories import (
    create_run,
    get_run,
    list_runs,
    save_error,
    save_node_output,
    update_run_status,
)


@pytest.fixture()
def session() -> Session:
    """Create an isolated in-memory database session for each repository test."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    with SessionLocal() as db_session:
        yield db_session


def test_create_and_get_run(session: Session) -> None:
    """create_run should persist the core run metadata."""
    created = create_run(
        session,
        run_id="run-001",
        session_id="anonymous",
        workflow_version="workflow-v1",
        prompt_version="prompt-v1",
        model_name="mock-model",
        input_brief={"company_or_product_name": "AI Tutor"},
    )

    fetched = get_run(session, "run-001")

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.status == "created"
    assert fetched.session_id == "anonymous"
    assert fetched.input_brief == {"company_or_product_name": "AI Tutor"}


def test_update_run_status(session: Session) -> None:
    """update_run_status should update an existing run."""
    create_run(session, run_id="run-002")

    updated = update_run_status(session, "run-002", "completed")

    assert updated.status == "completed"


def test_save_node_output(session: Session) -> None:
    """save_node_output should attach a workflow node snapshot to a run."""
    create_run(session, run_id="run-003")

    node_output = save_node_output(
        session,
        run_id="run-003",
        node_name="proposal_planner",
        input_snapshot={"brief": "sample"},
        output_snapshot={"outline": "sample outline"},
        token_usage={"prompt_tokens": 10},
    )
    fetched = get_run(session, "run-003")

    assert node_output.node_name == "proposal_planner"
    assert fetched is not None
    assert len(fetched.node_outputs) == 1
    assert fetched.node_outputs[0].output_snapshot == {"outline": "sample outline"}


def test_save_error(session: Session) -> None:
    """save_error should attach an error record to a run."""
    create_run(session, run_id="run-004")

    error_record = save_error(
        session,
        run_id="run-004",
        step_name="section_writer",
        error_type="ValueError",
        error_message="Invalid section output",
        stack_trace="Traceback...",
    )
    fetched = get_run(session, "run-004")

    assert error_record.error_type == "ValueError"
    assert fetched is not None
    assert len(fetched.errors) == 1
    assert fetched.errors[0].error_message == "Invalid section output"


def test_list_runs_returns_recent_runs_first(session: Session) -> None:
    """list_runs should return recent runs with an optional limit."""
    create_run(session, run_id="run-005")
    create_run(session, run_id="run-006")
    create_run(session, run_id="run-007")

    runs = list_runs(session, limit=2)

    assert [run.run_id for run in runs] == ["run-007", "run-006"]


def test_repository_raises_for_missing_run(session: Session) -> None:
    """Repository writes should fail clearly when the run id does not exist."""
    with pytest.raises(ValueError, match="Run not found: missing-run"):
        save_node_output(
            session,
            run_id="missing-run",
            node_name="input_validator",
        )
