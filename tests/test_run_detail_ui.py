"""Tests for Streamlit run detail helper data shaping."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import build_run_detail, summarize_evidence_sources
from storage.db import Base
from storage.repositories import (
    create_run,
    get_run,
    save_error,
    save_node_output,
    save_source_records,
)


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
    assert detail.sources == []
    assert len(detail.web_sources) == 1
    assert detail.web_sources[0]["agent"] == "Market Research Agent"
    assert detail.web_sources[0]["url"] == "https://example.com/market"


def test_summarize_evidence_sources_merges_sections_for_ui() -> None:
    """The UI should show one readable record per retrieved source."""
    summaries = summarize_evidence_sources(
        [
            {
                "source_id": "source-1",
                "text": "Framework excerpt",
                "score": 0.8,
                "metadata": {
                    "file_name": "framework.md",
                    "matched_sections": ["Market Opportunity"],
                },
            },
            {
                "source_id": "source-1",
                "text": "Another excerpt",
                "score": 0.9,
                "metadata": {
                    "file_name": "framework.md",
                    "matched_sections": ["Financial Assumptions"],
                },
            },
        ]
    )

    assert summaries == [
        {
            "source_id": "source-1",
            "file_name": "framework.md",
            "score": 0.9,
            "matched_sections": [
                "Market Opportunity",
                "Financial Assumptions",
            ],
            "quote": "Framework excerpt",
        }
    ]


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
    save_source_records(
        session,
        run_id="run-detail-001",
        sources=[
            {
                "source_id": "web-market-ui",
                "agent_name": "Market Research Agent",
                "query": "AI tutor market trends",
                "retrieved_at": "2026-07-25T10:00:00Z",
                "title": "AI tutor market report",
                "url": "https://example.com/market",
                "publisher": "Example Research",
                "published_date": "2026-06-01",
                "summary": "Market source rendered in the Streamlit table.",
                "relevance_score": 0.9,
                "source_quality": "research_org",
            }
        ],
    )
    session.commit()
