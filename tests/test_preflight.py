"""Tests for deterministic dependency checks before proposal generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from workflow.preflight import (
    PreflightError,
    check_preflight,
    run_preflight_checks,
)


def _ready_environment(*, tavily: bool = True) -> dict[str, str]:
    environment = {"GEMINI_API_KEY": "gemini-test-key"}
    if tavily:
        environment["TAVILY_API_KEY"] = "tavily-test-key"
    return environment


def test_preflight_reports_all_ready_dependencies(tmp_path: Path) -> None:
    """Configured keys and usable directories produce a ready status."""
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()
    output_dir = tmp_path / "generated" / "outputs"

    result = run_preflight_checks(
        environ=_ready_environment(),
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
    )

    assert result.is_ready
    assert not result.degraded
    assert result.gemini_available
    assert result.tavily_available
    assert result.knowledge_base_available
    assert result.output_writable
    assert output_dir.is_dir()


def test_missing_tavily_key_can_degrade_without_blocking(tmp_path: Path) -> None:
    """A run may explicitly continue with RAG-only evidence."""
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()

    result = run_preflight_checks(
        environ=_ready_environment(tavily=False),
        knowledge_base_dir=knowledge_base,
        output_dir=tmp_path / "outputs",
        allow_tavily_degradation=True,
    )

    assert result.is_ready
    assert result.degraded
    assert not result.tavily_available
    assert [issue.code for issue in result.warnings] == [
        "tavily_api_key_missing"
    ]


def test_missing_tavily_key_is_fatal_in_strict_mode(tmp_path: Path) -> None:
    """Strict callers can require web research before starting the workflow."""
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()

    with pytest.raises(PreflightError) as caught:
        run_preflight_checks(
            environ=_ready_environment(tavily=False),
            knowledge_base_dir=knowledge_base,
            output_dir=tmp_path / "outputs",
            allow_tavily_degradation=False,
        )

    assert [issue.code for issue in caught.value.result.errors] == [
        "tavily_api_key_missing"
    ]


def test_preflight_aggregates_mandatory_failures(tmp_path: Path) -> None:
    """The UI can display every fatal issue without repeated check cycles."""
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")

    result = check_preflight(
        environ={},
        knowledge_base_dir=tmp_path / "missing-knowledge-base",
        output_dir=output_file,
        allow_tavily_degradation=True,
    )

    assert not result.is_ready
    assert not result.gemini_available
    assert not result.knowledge_base_available
    assert not result.output_writable
    assert {issue.code for issue in result.errors} == {
        "gemini_api_key_missing",
        "knowledge_base_unavailable",
        "output_directory_not_writable",
    }
    assert [issue.code for issue in result.warnings] == [
        "tavily_api_key_missing"
    ]


def test_preflight_can_require_an_existing_output_directory(
    tmp_path: Path,
) -> None:
    """Read-only checks do not create an output directory when disabled."""
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()
    output_dir = tmp_path / "missing-outputs"

    result = check_preflight(
        environ=_ready_environment(),
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        create_output_dir=False,
    )

    assert not result.output_writable
    assert not output_dir.exists()
    assert result.errors[0].code == "output_directory_unavailable"


def test_revision_only_preflight_does_not_require_knowledge_base(
    tmp_path: Path,
) -> None:
    """A persisted Revision checkpoint must not rerun or require retrieval."""
    result = run_preflight_checks(
        environ=_ready_environment(),
        knowledge_base_dir=tmp_path / "missing-knowledge-base",
        output_dir=tmp_path / "outputs",
        require_knowledge_base=False,
    )

    assert result.is_ready
    assert result.knowledge_base_available
