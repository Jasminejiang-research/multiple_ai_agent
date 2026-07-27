"""Tests for the isolated SLM command-line entry point."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from workflow.preflight import PreflightIssue

from slm import cli
from slm.preflight_slm import SLMPreflightResult


def _preflight(
    *issues: PreflightIssue,
) -> SLMPreflightResult:
    return SLMPreflightResult(
        slm_endpoint_available=not any(
            issue.code == "slm_endpoint_unreachable" for issue in issues
        ),
        tavily_available=True,
        knowledge_base_available=True,
        output_writable=True,
        knowledge_base_dir=Path("knowledge_base"),
        output_dir=Path("outputs"),
        issues=issues,
    )


def test_main_preflights_then_runs_and_prints_summary(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    input_path = tmp_path / "brief.json"
    input_path.write_text(
        json.dumps({"company_or_product_name": "Example"}),
        encoding="utf-8",
    )
    events: list[object] = []

    def fake_preflight(**kwargs):
        events.append(("preflight", kwargs))
        return _preflight()

    def fake_workflow(payload):
        events.append(("run", payload))
        return SimpleNamespace(
            run_id="slm-run-001",
            output_path=Path("outputs/result.md"),
        )

    monkeypatch.setattr(cli, "check_slm_preflight", fake_preflight)
    monkeypatch.setattr(cli, "run_slm_workflow", fake_workflow)
    monkeypatch.setattr(
        cli,
        "_persisted_token_usage",
        lambda run_id: {
            "request_count": 2,
            "retry_count": 0,
            "prompt_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "approximate_cost": 0.0,
        },
    )

    exit_code = cli.main(
        ["--mode", "workflow", "--input", str(input_path)]
    )

    assert exit_code == 0
    assert events == [
        ("preflight", {"require_knowledge_base": False}),
        ("run", {"company_or_product_name": "Example"}),
    ]
    stdout = capsys.readouterr().out
    assert "run_id: slm-run-001" in stdout
    assert f"output_path: {Path('outputs/result.md')}" in stdout
    assert "elapsed_seconds:" in stdout
    assert '"total_tokens": 15' in stdout


def test_main_stops_before_reading_input_when_preflight_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    missing_input = tmp_path / "missing.json"
    issue = PreflightIssue(
        code="slm_endpoint_unreachable",
        message="请确认 ollama serve 已启动。",
    )
    monkeypatch.setattr(
        cli,
        "check_slm_preflight",
        lambda **kwargs: _preflight(issue),
    )
    monkeypatch.setattr(
        cli,
        "run_slm_multi_agent",
        lambda payload: (_ for _ in ()).throw(
            AssertionError("pipeline must not run")
        ),
    )

    exit_code = cli.main(
        ["--mode", "multi", "--input", str(missing_input)]
    )

    assert exit_code != 0
    stderr = capsys.readouterr().err
    assert "slm_endpoint_unreachable" in stderr
    assert "ollama serve" in stderr


def test_main_reports_invalid_mode_input_after_successful_preflight(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    input_path = tmp_path / "brief.json"
    input_path.write_text('["not", "an", "object"]', encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "check_slm_preflight",
        lambda **kwargs: _preflight(),
    )

    exit_code = cli.main(
        ["--mode", "workflow", "--input", str(input_path)]
    )

    assert exit_code == 2
    assert "workflow input must be a JSON object" in capsys.readouterr().err
