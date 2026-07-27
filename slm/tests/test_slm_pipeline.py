"""Tests for isolated SLM pipeline orchestration and injection."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

import slm.pipeline as pipeline
from slm.config import SLMConfig
from tools.tavily_search import WebSearchConfigurationError
from workflow.preflight import PreflightError, PreflightIssue


@pytest.fixture
def config() -> SLMConfig:
    return SLMConfig(
        base_url="http://slm.test/v1",
        model_name="qwen-test",
        api_key="test-key",
        structured_mode="json_object",
        max_prompt_chars=60_000,
        max_output_tokens=8_192,
        run_max_requests=12,
        run_max_total_tokens=160_000,
        request_timeout=300,
    )


@pytest.fixture
def adapters() -> dict[str, object]:
    return {
        "planner": object(),
        "section_writer": object(),
        "basic_critic": object(),
        "revision": object(),
        "research": object(),
        "strategy": object(),
        "finance": object(),
        "writer": object(),
        "critic": object(),
    }


@pytest.fixture
def ready_preflight() -> SimpleNamespace:
    return SimpleNamespace(
        is_ready=True,
        errors=(),
        warnings=(PreflightIssue("optional", "optional warning", True),),
        tavily_available=True,
    )


@pytest.fixture
def pipeline_harness(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
    adapters: dict[str, object],
    ready_preflight: SimpleNamespace,
) -> dict[str, Any]:
    captured: dict[str, Any] = {
        "created_runs": [],
        "statuses": [],
        "commits": 0,
    }

    class FakeSession:
        def commit(self) -> None:
            captured["commits"] += 1

    @contextmanager
    def fake_session() -> Iterator[FakeSession]:
        yield FakeSession()

    def fake_create_run(_session: FakeSession, **kwargs: Any) -> None:
        captured["created_runs"].append(kwargs)

    def fake_update_run_status(
        _session: FakeSession,
        run_id: str,
        status: str,
    ) -> None:
        captured["statuses"].append((run_id, status))

    monkeypatch.setattr(pipeline, "load_slm_config", lambda: config)
    monkeypatch.setattr(
        pipeline,
        "check_slm_preflight",
        lambda **_kwargs: ready_preflight,
    )
    monkeypatch.setattr(pipeline, "_ensure_run_history_tables", lambda: None)
    monkeypatch.setattr(pipeline, "get_session", fake_session)
    monkeypatch.setattr(pipeline, "create_run", fake_create_run)
    monkeypatch.setattr(pipeline, "update_run_status", fake_update_run_status)
    monkeypatch.setattr(
        pipeline,
        "_set_run_status",
        lambda run_id, status: captured["statuses"].append((run_id, status)),
    )
    monkeypatch.setattr(
        pipeline,
        "_get_step_statuses",
        lambda _run_id: [{"step": "test", "status": "completed"}],
    )
    monkeypatch.setattr(pipeline, "build_slm_adapters", lambda _config: adapters)
    return captured


def test_baseline_reuses_generator_and_records_slm_model(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
    pipeline_harness: dict[str, Any],
) -> None:
    client = object()
    proposal = object()
    generation: dict[str, Any] = {}
    monkeypatch.setattr(pipeline, "SLMClient", lambda received: client)

    def fake_generate(received_client: object, user_idea: str) -> object:
        generation.update(client=received_client, user_idea=user_idea)
        return proposal

    monkeypatch.setattr(pipeline, "generate_proposal", fake_generate)
    monkeypatch.setattr(
        pipeline,
        "proposal_to_markdown",
        lambda received: "# proposal" if received is proposal else "",
    )
    monkeypatch.setattr(
        pipeline,
        "save_proposal_markdown",
        lambda received: Path("proposal.md"),
    )

    result = pipeline.run_slm_baseline("A concise business idea")

    assert generation == {
        "client": client,
        "user_idea": "A concise business idea",
    }
    assert result.markdown == "# proposal"
    assert pipeline_harness["created_runs"][0]["model_name"] == config.model_name


def test_workflow_injects_four_adapters_and_slm_budget(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
    adapters: dict[str, object],
    pipeline_harness: dict[str, Any],
) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            captured["state"] = state
            captured["graph_result"] = {
                "final_markdown": "# workflow",
                "output_path": "workflow.md",
            }
            return captured["graph_result"]

    def fake_builder(**kwargs: Any) -> FakeGraph:
        captured["builder_kwargs"] = kwargs
        return FakeGraph()

    monkeypatch.setattr(pipeline, "build_proposal_workflow_graph", fake_builder)

    result = pipeline.run_slm_workflow({"company_name": "Test Co"})

    injected = {
        key: value
        for key, value in captured["builder_kwargs"].items()
        if key.endswith("_llm")
    }
    assert injected == {
        "planner_llm": adapters["planner"],
        "section_writer_llm": adapters["section_writer"],
        "critic_llm": adapters["basic_critic"],
        "revision_llm": adapters["revision"],
    }
    assert captured["graph_result"]["run_budget"]["max_requests"] == (
        config.run_max_requests
    )
    assert captured["graph_result"]["run_budget"]["max_total_tokens"] == (
        config.run_max_total_tokens
    )
    assert result.markdown == "# workflow"
    assert pipeline_harness["created_runs"][0]["model_name"] == config.model_name


def test_multi_agent_injects_every_active_adapter_and_no_web_fallback(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
    adapters: dict[str, object],
    ready_preflight: SimpleNamespace,
    pipeline_harness: dict[str, Any],
) -> None:
    ready_preflight.tavily_available = False
    captured: dict[str, Any] = {}

    class FakeGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            captured["state"] = state
            return {
                "final_markdown": "# multi",
                "output_path": "multi.md",
                "evidence_chunks": [],
                "web_sources": [],
            }

    def fake_builder(**kwargs: Any) -> FakeGraph:
        captured["builder_kwargs"] = kwargs
        return FakeGraph()

    monkeypatch.setattr(
        pipeline,
        "build_multi_agent_workflow_graph",
        fake_builder,
    )

    result = pipeline.run_slm_multi_agent({"company_name": "Test Co"})

    injected = {
        key: value
        for key, value in captured["builder_kwargs"].items()
        if key.endswith("_llm")
    }
    assert injected == {
        "research_llm": adapters["research"],
        "strategy_llm": adapters["strategy"],
        "finance_llm": adapters["finance"],
        "writer_llm": adapters["writer"],
        "critic_llm": adapters["critic"],
        "revision_llm": adapters["revision"],
    }
    with pytest.raises(WebSearchConfigurationError):
        captured["builder_kwargs"]["web_search_tool"]("query", None, None, 3)
    assert result.markdown == "# multi"
    assert pipeline_harness["created_runs"][0]["model_name"] == config.model_name


@pytest.mark.parametrize(
    "runner,input_value",
    [
        ("run_slm_baseline", "idea"),
        ("run_slm_workflow", {"company_name": "Test Co"}),
        ("run_slm_multi_agent", {"company_name": "Test Co"}),
    ],
)
def test_preflight_failure_stops_before_llm_or_graph(
    monkeypatch: pytest.MonkeyPatch,
    config: SLMConfig,
    runner: str,
    input_value: object,
) -> None:
    failed_preflight = SimpleNamespace(
        is_ready=False,
        errors=(PreflightIssue("slm_endpoint_unreachable", "offline"),),
        warnings=(),
        tavily_available=False,
    )
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "load_slm_config", lambda: config)
    monkeypatch.setattr(
        pipeline,
        "check_slm_preflight",
        lambda **_kwargs: failed_preflight,
    )
    monkeypatch.setattr(
        pipeline,
        "SLMClient",
        lambda _config: calls.append("client"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_slm_adapters",
        lambda _config: calls.append("adapters"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_proposal_workflow_graph",
        lambda **_kwargs: calls.append("workflow_graph"),
    )
    monkeypatch.setattr(
        pipeline,
        "build_multi_agent_workflow_graph",
        lambda **_kwargs: calls.append("multi_graph"),
    )

    with pytest.raises(PreflightError):
        getattr(pipeline, runner)(input_value)

    assert calls == []
