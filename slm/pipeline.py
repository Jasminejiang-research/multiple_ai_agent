"""Orchestration shell for the three isolated SLM execution modes.

Private ``app.py`` dependency checklist (review whenever ``app.py`` changes):
``_ensure_run_history_tables``, ``_set_run_status``, and
``_get_step_statuses``. Public helpers reused here are
``WorkflowPipelineResult``, ``generate_proposal``,
``summarize_evidence_sources``, and ``summarize_web_sources``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import (
    OUTPUT_DIR,
    ROOT_DIR,
    WorkflowPipelineResult,
    _ensure_run_history_tables,
    _get_step_statuses,
    _set_run_status,
    generate_proposal,
    proposal_to_markdown,
    save_proposal_markdown,
    summarize_evidence_sources,
    summarize_web_sources,
)
from storage.db import get_session
from storage.repositories import create_run, update_run_status
from tools.tavily_search import WebSearchConfigurationError
from workflow.graph import build_proposal_workflow_graph
from workflow.logging import (
    MULTI_AGENT_PROMPT_VERSION,
    MULTI_AGENT_VERSION,
    PROMPT_VERSION,
    WORKFLOW_VERSION,
)
from workflow.multi_agent_graph import build_multi_agent_workflow_graph
from workflow.preflight import PreflightError
from workflow.run_budget import run_budget

from slm.client import SLMClient
from slm.config import SLMConfig, load_slm_config
from slm.factories import build_slm_adapters
from slm.preflight_slm import SLMPreflightResult, check_slm_preflight


BASELINE_WORKFLOW_VERSION = "single-agent-baseline-v1"
BASELINE_PROMPT_VERSION = "phase1-single-agent-prompt-v1"


def _require_ready(preflight: SLMPreflightResult) -> SLMPreflightResult:
    """Raise before persistence or model construction when preflight fails."""
    if not preflight.is_ready:
        raise PreflightError(preflight)
    return preflight


def _run_slm_preflight(
    config: SLMConfig,
    *,
    require_knowledge_base: bool,
) -> SLMPreflightResult:
    """Run the SLM-specific dependency checks with application paths."""
    return _require_ready(
        check_slm_preflight(
            base_url=config.base_url,
            knowledge_base_dir=ROOT_DIR / "knowledge_base",
            output_dir=OUTPUT_DIR,
            require_knowledge_base=require_knowledge_base,
        )
    )


def _create_running_run(
    *,
    config: SLMConfig,
    workflow_version: str,
    prompt_version: str,
    input_brief: dict[str, Any],
) -> str:
    """Create the same run-history record shape used by the existing pipelines."""
    _ensure_run_history_tables()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    with get_session() as session:
        create_run(
            session,
            run_id=run_id,
            session_id="streamlit",
            workflow_version=workflow_version,
            prompt_version=prompt_version,
            model_name=config.model_name,
            input_brief=input_brief,
        )
        update_run_status(session, run_id, "running")
        session.commit()
    return run_id


def _baseline_input(
    user_brief_or_idea: str | Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Normalize either supported baseline input shape without changing content."""
    if isinstance(user_brief_or_idea, str):
        return user_brief_or_idea, {"user_idea": user_brief_or_idea}
    brief = dict(user_brief_or_idea)
    return json.dumps(brief, ensure_ascii=False, indent=2), brief


def run_slm_baseline(
    user_brief_or_idea: str | Mapping[str, Any],
) -> WorkflowPipelineResult:
    """Run the single-agent baseline through the shared proposal generator."""
    config = load_slm_config()
    _run_slm_preflight(config, require_knowledge_base=False)
    user_idea, input_brief = _baseline_input(user_brief_or_idea)
    run_id = _create_running_run(
        config=config,
        workflow_version=BASELINE_WORKFLOW_VERSION,
        prompt_version=BASELINE_PROMPT_VERSION,
        input_brief=input_brief,
    )

    try:
        with run_budget(
            max_requests=config.run_max_requests,
            max_total_tokens=config.run_max_total_tokens,
        ):
            proposal = generate_proposal(SLMClient(config), user_idea)
        markdown = proposal_to_markdown(proposal)
        output_path = save_proposal_markdown(proposal)
    except Exception:
        _set_run_status(run_id, "failed")
        raise

    _set_run_status(run_id, "completed")
    return WorkflowPipelineResult(
        output_path=output_path,
        markdown=markdown,
        run_id=run_id,
        step_statuses=_get_step_statuses(run_id),
        sources=[],
        web_sources=[],
    )


def run_slm_workflow(user_brief: dict[str, str]) -> WorkflowPipelineResult:
    """Run the deterministic workflow with four injected SLM adapters."""
    config = load_slm_config()
    preflight = _run_slm_preflight(config, require_knowledge_base=False)
    run_id = _create_running_run(
        config=config,
        workflow_version=WORKFLOW_VERSION,
        prompt_version=PROMPT_VERSION,
        input_brief=user_brief,
    )
    adapters = build_slm_adapters(config)
    graph = build_proposal_workflow_graph(
        planner_llm=adapters["planner"],
        section_writer_llm=adapters["section_writer"],
        critic_llm=adapters["basic_critic"],
        revision_llm=adapters["revision"],
        logging_session_factory=get_session,
    )

    with run_budget(
        max_requests=config.run_max_requests,
        max_total_tokens=config.run_max_total_tokens,
    ) as budget:
        result = graph.invoke(
            {
                "run_id": run_id,
                "user_brief": user_brief,
                "preflight_warnings": [
                    issue.message for issue in preflight.warnings
                ],
            }
        )
        result["run_budget"] = budget.snapshot()

    if result.get("missing_info"):
        _set_run_status(run_id, "needs_input")
        raise ValueError("Input incomplete: " + "; ".join(result["missing_info"]))

    markdown = result.get("final_markdown") or result.get("markdown")
    if not markdown:
        _set_run_status(run_id, "failed")
        raise ValueError("Workflow finished without producing a Markdown proposal.")

    _set_run_status(run_id, "completed")
    return WorkflowPipelineResult(
        output_path=Path(result["output_path"]),
        markdown=markdown,
        run_id=run_id,
        step_statuses=_get_step_statuses(run_id),
        sources=[],
        web_sources=[],
    )


def run_slm_multi_agent(user_brief: dict[str, str]) -> WorkflowPipelineResult:
    """Run the controlled multi-agent graph with every active SLM LLM seam."""
    config = load_slm_config()
    preflight = _run_slm_preflight(config, require_knowledge_base=True)
    run_id = _create_running_run(
        config=config,
        workflow_version=MULTI_AGENT_VERSION,
        prompt_version=MULTI_AGENT_PROMPT_VERSION,
        input_brief=user_brief,
    )
    adapters = build_slm_adapters(config)
    graph_kwargs: dict[str, Any] = {
        "research_llm": adapters["research"],
        "strategy_llm": adapters["strategy"],
        "finance_llm": adapters["finance"],
        "writer_llm": adapters["writer"],
        "critic_llm": adapters["critic"],
        "revision_llm": adapters["revision"],
        "logging_session_factory": get_session,
    }
    if not preflight.tavily_available:

        def no_web_search(
            query: str,
            allowed_domains: list[str] | None,
            recency: str | None,
            max_results: int,
        ) -> list[Any]:
            """Explicit preflight degradation: no provider call is attempted."""
            _ = (query, allowed_domains, recency, max_results)
            raise WebSearchConfigurationError(
                "Tavily disabled by preflight; continuing without Web evidence."
            )

        graph_kwargs["web_search_tool"] = no_web_search

    graph = build_multi_agent_workflow_graph(**graph_kwargs)
    with run_budget(
        max_requests=config.run_max_requests,
        max_total_tokens=config.run_max_total_tokens,
    ) as budget:
        result = graph.invoke(
            {
                "run_id": run_id,
                "user_brief": user_brief,
                "preflight_warnings": [
                    issue.message for issue in preflight.warnings
                ],
            }
        )
        result["run_budget"] = budget.snapshot()

    if result.get("missing_info"):
        _set_run_status(run_id, "needs_input")
        raise ValueError("Input incomplete: " + "; ".join(result["missing_info"]))

    markdown = result.get("final_markdown") or result.get("markdown")
    if not markdown:
        _set_run_status(run_id, "failed")
        raise ValueError(
            "Multi-agent workflow finished without a Markdown proposal."
        )

    _set_run_status(run_id, "completed")
    return WorkflowPipelineResult(
        output_path=Path(result["output_path"]),
        markdown=markdown,
        run_id=run_id,
        step_statuses=_get_step_statuses(run_id),
        sources=summarize_evidence_sources(result.get("evidence_chunks", [])),
        web_sources=summarize_web_sources(result.get("web_sources", [])),
    )


__all__ = [
    "run_slm_baseline",
    "run_slm_multi_agent",
    "run_slm_workflow",
]
