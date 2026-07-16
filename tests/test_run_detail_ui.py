"""Tests for Streamlit run detail helper data shaping."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import build_run_detail
from storage.db import Base
from storage.repositories import create_run, get_run, save_error, save_node_output


def test_build_run_detail_includes_brief_nodes_errors_and_output_path() -> None:
    """Run detail should expose the data required by the Streamlit detail UI."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    with SessionLocal() as session:
        _create_logged_run(session)
        run = get_run(session, "run-detail-001")

        assert run is not None
        detail = build_run_detail(run)

    assert detail.run_id == "run-detail-001"
    assert detail.status == "created"
    assert detail.input_brief == {"company_or_product_name": "AI Tutor"}
    assert [node.step for node in detail.node_outputs] == ["input_validator", "export"]
    assert detail.node_outputs[0].status == "completed"
    assert "current_step" in detail.node_outputs[0].output_preview
    assert detail.error_messages == ["export: ValueError: Export failed"]
    assert detail.final_output_path == "outputs/ai_tutor.md"


def _create_logged_run(session: Session) -> None:
    """Persist a minimal run with node output and error records."""
    create_run(
        session,
        run_id="run-detail-001",
        input_brief={"company_or_product_name": "AI Tutor"},
    )
    save_node_output(
        session,
        run_id="run-detail-001",
        node_name="input_validator",
        output_snapshot={
            "status": "completed",
            "output": {"missing_info": [], "current_step": "input_validator"},
        },
    )
    save_node_output(
        session,
        run_id="run-detail-001",
        node_name="export",
        output_snapshot={
            "status": "completed",
            "output": {"output_path": "outputs/ai_tutor.md"},
        },
    )
    save_error(
        session,
        run_id="run-detail-001",
        step_name="export",
        error_type="ValueError",
        error_message="Export failed",
    )
    session.commit()
