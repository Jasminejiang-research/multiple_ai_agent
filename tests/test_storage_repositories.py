"""Tests for repository helpers that persist run history."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.db import Base
from storage.repositories import (
    add_run_token_usage,
    create_run,
    get_latest_node_input,
    get_run,
    list_runs,
    save_agent_output,
    save_error,
    save_node_output,
    save_source_records,
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


def test_latest_revision_input_is_a_resumable_checkpoint(session: Session) -> None:
    """Only the latest persisted Revision input should be resumed."""
    create_run(session, run_id="run-revision-checkpoint")
    save_node_output(
        session,
        run_id="run-revision-checkpoint",
        node_name="revision",
        input_snapshot={"proposal_draft": {"title": "old"}},
    )
    save_node_output(
        session,
        run_id="run-revision-checkpoint",
        node_name="revision",
        input_snapshot={"proposal_draft": {"title": "latest"}},
    )

    checkpoint = get_latest_node_input(
        session,
        run_id="run-revision-checkpoint",
        node_name="revision",
    )

    assert checkpoint == {"proposal_draft": {"title": "latest"}}


def test_add_run_token_usage_accumulates_requests_retries_and_cost(
    session: Session,
) -> None:
    """Run history should expose free-tier request and token consumption."""
    create_run(session, run_id="run-usage-001")

    add_run_token_usage(
        session,
        "run-usage-001",
        {
            "request_count": 2,
            "retry_count": 1,
            "prompt_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "approximate_cost": 0.001,
        },
    )
    add_run_token_usage(
        session,
        "run-usage-001",
        {
            "request_count": 1,
            "retry_count": 0,
            "prompt_tokens": 50,
            "output_tokens": 10,
            "total_tokens": 60,
            "approximate_cost": 0.0005,
        },
    )

    run = get_run(session, "run-usage-001")
    assert run is not None
    assert run.token_usage == {
        "request_count": 3,
        "retry_count": 1,
        "prompt_tokens": 150,
        "output_tokens": 30,
        "total_tokens": 180,
        "approximate_cost": 0.0015,
    }
    assert run.approximate_cost == 0.0015


def test_save_agent_output(session: Session) -> None:
    """save_agent_output should attach a structured agent result to a run."""
    create_run(session, run_id="run-agent-001")

    agent_output = save_agent_output(
        session,
        run_id="run-agent-001",
        agent_name="Research Agent",
        output_type="ResearchAnalysis",
        output_payload={"analysis_summary": "Sample structured research output."},
    )
    fetched = get_run(session, "run-agent-001")

    assert agent_output.output_type == "ResearchAnalysis"
    assert fetched is not None
    assert len(fetched.agent_outputs) == 1
    assert fetched.agent_outputs[0].agent_name == "Research Agent"


def test_save_source_records_persists_every_web_result(session: Session) -> None:
    """Every market and competitor result should remain attached to its run."""
    create_run(session, run_id="run-sources-001")
    retrieved_at = datetime.now(timezone.utc)

    records = save_source_records(
        session,
        run_id="run-sources-001",
        sources=[
            {
                "source_id": "web-market-1",
                "agent_name": "Market Research Agent",
                "query": "AI education market trends",
                "retrieved_at": retrieved_at,
                "title": "Market report",
                "url": "https://example.com/market",
                "publisher": "Example Research",
                "published_date": "2026-06-01",
                "summary": "Current market evidence.",
                "relevance_score": 0.9,
                "source_quality": "research_org",
            },
            {
                "source_id": "web-competitor-1",
                "agent_name": "Competitor Agent",
                "query": "AI education competitors",
                "retrieved_at": retrieved_at,
                "title": "Competitor directory",
                "url": "https://example.com/competitors",
                "publisher": "Example Research",
                "published_date": "2026-05-01",
                "summary": "Current competitor evidence.",
                "relevance_score": 0.8,
                "source_quality": "research_org",
            },
        ],
    )
    fetched = get_run(session, "run-sources-001")

    assert len(records) == 2
    assert fetched is not None
    assert [source.source_id for source in fetched.sources] == [
        "web-market-1",
        "web-competitor-1",
    ]


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
