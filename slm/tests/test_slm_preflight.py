"""Tests for the isolated SLM preflight checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

import slm.preflight_slm as preflight_module
from slm.preflight_slm import check_slm_preflight


class _ReachableResponse:
    def raise_for_status(self) -> None:
        return None


def _dependency_paths(tmp_path: Path) -> tuple[Path, Path]:
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()
    return knowledge_base, tmp_path / "outputs"


def test_reachable_endpoint_produces_ready_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    request: dict[str, Any] = {}

    def fake_get(url: str, *, timeout: int) -> _ReachableResponse:
        request.update(url=url, timeout=timeout)
        return _ReachableResponse()

    monkeypatch.setattr(preflight_module.requests, "get", fake_get)

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1/",
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
    )

    assert result.is_ready
    assert not result.degraded
    assert result.slm_endpoint_available
    assert request == {
        "url": "http://localhost:11434/v1/models",
        "timeout": 3,
    }
    assert "gemini_api_key_missing" not in {
        issue.code for issue in result.issues
    }


def test_unreachable_endpoint_is_a_fatal_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)

    def fail_get(url: str, *, timeout: int) -> _ReachableResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(preflight_module.requests, "get", fail_get)

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
    )

    assert not result.is_ready
    assert not result.slm_endpoint_available
    assert [issue.code for issue in result.errors] == [
        "slm_endpoint_unreachable"
    ]
    assert "请确认 ollama serve 已启动" in result.errors[0].message


def test_missing_tavily_key_remains_a_degraded_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    monkeypatch.setattr(
        preflight_module.requests,
        "get",
        lambda url, *, timeout: _ReachableResponse(),
    )

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        environ={},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
    )

    assert result.is_ready
    assert result.degraded
    assert not result.tavily_available
    assert [issue.code for issue in result.warnings] == [
        "tavily_api_key_missing"
    ]


def test_missing_knowledge_base_remains_a_fatal_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        preflight_module.requests,
        "get",
        lambda url, *, timeout: _ReachableResponse(),
    )

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=tmp_path / "missing-knowledge-base",
        output_dir=tmp_path / "outputs",
    )

    assert not result.is_ready
    assert not result.knowledge_base_available
    assert [issue.code for issue in result.errors] == [
        "knowledge_base_unavailable"
    ]
