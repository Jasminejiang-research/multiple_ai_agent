"""Tests for the isolated SLM preflight checks."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import requests

import slm.preflight_slm as preflight_module
from slm.config import SLMConfig
from slm.preflight_slm import check_slm_preflight


class _ReachableResponse:
    def raise_for_status(self) -> None:
        return None


@pytest.fixture(autouse=True)
def isolated_context_window_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Never read or write the developer's real measurement cache."""
    monkeypatch.setattr(
        preflight_module,
        "CONTEXT_WINDOW_CACHE_PATH",
        tmp_path / "context_window_cache.json",
    )


def _dependency_paths(tmp_path: Path) -> tuple[Path, Path]:
    knowledge_base = tmp_path / "knowledge-base"
    knowledge_base.mkdir()
    return knowledge_base, tmp_path / "outputs"


def _config(*, context_probe: bool = False) -> SLMConfig:
    return SLMConfig(
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:3b",
        api_key="ollama",
        structured_mode="json_object",
        max_prompt_chars=60_000,
        max_output_tokens=8_192,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=900,
        context_probe=context_probe,
    )


def test_reachable_endpoint_produces_ready_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    request: dict[str, Any] = {}

    def fake_get(url: str, *, timeout: int, headers: dict) -> _ReachableResponse:
        request.update(url=url, timeout=timeout, headers=headers)
        return _ReachableResponse()

    monkeypatch.setattr(preflight_module.requests, "get", fake_get)

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1/",
        config=_config(),
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
        # Hosted endpoints answer an unauthenticated /models with 401, which
        # this check would otherwise report as an unreachable endpoint.
        "headers": {"Authorization": "Bearer ollama"},
    }
    assert "gemini_api_key_missing" not in {
        issue.code for issue in result.issues
    }


def test_unreachable_endpoint_is_a_fatal_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)

    def fail_get(url: str, *, timeout: int, headers: dict) -> _ReachableResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(preflight_module.requests, "get", fail_get)

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        config=_config(),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
    )

    assert not result.is_ready
    assert not result.slm_endpoint_available
    assert [issue.code for issue in result.errors] == [
        "slm_endpoint_unreachable"
    ]
    assert "请确认 SLM_BASE_URL 正确" in result.errors[0].message


def test_missing_tavily_key_remains_a_degraded_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    monkeypatch.setattr(
        preflight_module.requests,
        "get",
        lambda url, *, timeout, headers=None: _ReachableResponse(),
    )

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        config=_config(),
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
        lambda url, *, timeout, headers=None: _ReachableResponse(),
    )

    result = check_slm_preflight(
        base_url="http://localhost:11434/v1",
        config=_config(),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=tmp_path / "missing-knowledge-base",
        output_dir=tmp_path / "outputs",
    )

    assert not result.is_ready
    assert not result.knowledge_base_available
    assert [issue.code for issue in result.errors] == [
        "knowledge_base_unavailable"
    ]


def _reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        preflight_module.requests,
        "get",
        lambda url, *, timeout, headers=None: _ReachableResponse(),
    )


def test_sufficient_context_window_is_probed_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)
    probed: list[int] = []

    def probe(config: SLMConfig) -> int:
        probed.append(config.max_output_tokens)
        return 32_768

    result = check_slm_preflight(
        config=_config(context_probe=True),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=probe,
    )

    assert probed == [8_192]
    assert result.is_ready
    assert result.context_window_tokens == 32_768


def test_undersized_context_window_is_a_fatal_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The 2048-token Ollama default must stop the run instead of truncating."""
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)

    result = check_slm_preflight(
        config=_config(context_probe=True),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=lambda config: 2_050,
    )

    assert not result.is_ready
    assert result.context_window_tokens == 2_050
    assert [issue.code for issue in result.errors] == [
        "slm_context_window_too_small"
    ]
    message = result.errors[0].message
    assert "2050" in message and "23192" in message
    assert "num_ctx" in message


def test_failed_context_probe_is_a_fatal_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)

    def failing_probe(config: SLMConfig) -> int:
        raise TimeoutError("probe timed out")

    result = check_slm_preflight(
        config=_config(context_probe=True),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=failing_probe,
    )

    assert not result.is_ready
    assert result.context_window_tokens is None
    assert [issue.code for issue in result.errors] == [
        "slm_context_window_unverified"
    ]
    assert "SLM_CONTEXT_PROBE=0" in result.errors[0].message


def test_disabled_context_probe_skips_the_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)

    def unexpected_probe(config: SLMConfig) -> int:
        raise AssertionError("probe must not run when SLM_CONTEXT_PROBE is off")

    result = check_slm_preflight(
        config=_config(context_probe=False),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=unexpected_probe,
    )

    assert result.is_ready
    assert result.context_window_tokens is None


def test_measured_window_is_cached_and_reused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Only the first run of a configuration pays for the measurement."""
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)
    probe_calls: list[str] = []

    def probe(config: SLMConfig) -> int:
        probe_calls.append(config.model_name)
        return 32_768

    def run() -> Any:
        return check_slm_preflight(
            config=_config(context_probe=True),
            environ={"TAVILY_API_KEY": "test-key"},
            knowledge_base_dir=knowledge_base,
            output_dir=output_dir,
            context_window_probe=probe,
        )

    assert run().context_window_tokens == 32_768
    assert run().context_window_tokens == 32_768
    assert probe_calls == ["qwen2.5:3b"]


def test_cache_is_keyed_by_model_so_a_new_model_is_remeasured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)
    windows = {"qwen2.5:3b": 2_050, "qwen2.5-3b-32k": 32_768}
    probe_calls: list[str] = []

    def probe(config: SLMConfig) -> int:
        probe_calls.append(config.model_name)
        return windows[config.model_name]

    def run(model_name: str) -> Any:
        return check_slm_preflight(
            config=dataclasses.replace(
                _config(context_probe=True),
                model_name=model_name,
            ),
            environ={"TAVILY_API_KEY": "test-key"},
            knowledge_base_dir=knowledge_base,
            output_dir=output_dir,
            context_window_probe=probe,
        )

    assert not run("qwen2.5:3b").is_ready
    assert run("qwen2.5-3b-32k").is_ready
    assert probe_calls == ["qwen2.5:3b", "qwen2.5-3b-32k"]


def test_unusable_cache_file_falls_back_to_probing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge_base, output_dir = _dependency_paths(tmp_path)
    _reachable(monkeypatch)
    preflight_module.CONTEXT_WINDOW_CACHE_PATH.write_text(
        "not json", encoding="utf-8"
    )

    result = check_slm_preflight(
        config=_config(context_probe=True),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=lambda config: 32_768,
    )

    assert result.is_ready
    assert result.context_window_tokens == 32_768


def test_unreachable_endpoint_skips_the_context_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A dead endpoint must report one root cause, not two."""
    knowledge_base, output_dir = _dependency_paths(tmp_path)

    def fail_get(url: str, *, timeout: int, headers: dict) -> _ReachableResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(preflight_module.requests, "get", fail_get)

    def unexpected_probe(config: SLMConfig) -> int:
        raise AssertionError("probe must not run against a dead endpoint")

    result = check_slm_preflight(
        config=_config(context_probe=True),
        environ={"TAVILY_API_KEY": "test-key"},
        knowledge_base_dir=knowledge_base,
        output_dir=output_dir,
        context_window_probe=unexpected_probe,
    )

    assert [issue.code for issue in result.errors] == [
        "slm_endpoint_unreachable"
    ]
