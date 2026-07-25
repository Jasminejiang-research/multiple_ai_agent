"""Open Proposal Agent — Phase 1 single-agent baseline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from schemas.proposal_schema import BusinessProposal
from workflow.llm_client import LLMClient
from storage.db import Base, engine, get_session
from storage.repositories import create_run, get_run, list_runs, update_run_status
from workflow.graph import build_proposal_workflow_graph
from workflow.logging import (
    MULTI_AGENT_PROMPT_VERSION,
    MULTI_AGENT_VERSION,
    PROMPT_VERSION,
    WORKFLOW_VERSION,
    step_names_for_workflow,
    summarize_step_statuses,
)
from workflow.multi_agent_graph import build_multi_agent_workflow_graph

ROOT_DIR = Path(__file__).resolve().parent
PROMPT_PATH = ROOT_DIR / "prompts" / "single_agent_proposal.md"
OUTPUT_DIR = ROOT_DIR / "outputs"
MODEL_NAME = "gemini-2.5-flash"


@dataclass(frozen=True)
class WorkflowPipelineResult:
    """Streamlit-facing summary of a persisted workflow run."""

    output_path: Path
    markdown: str
    run_id: str
    step_statuses: list[dict[str, str]]
    sources: list[dict[str, Any]] = field(default_factory=list)
    web_sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RunSummary:
    """Compact run metadata for the recent runs sidebar."""

    run_id: str
    label: str
    status: str


@dataclass(frozen=True)
class NodeOutputPreview:
    """Streamlit-facing preview of one workflow node's latest log entry."""

    step: str
    status: str
    output_preview: str
    prompt_version: str = ""


@dataclass(frozen=True)
class RunDetail:
    """Full run detail data needed by the Streamlit run detail view."""

    run_id: str
    status: str
    input_brief: dict[str, Any] | None
    node_outputs: list[NodeOutputPreview]
    error_messages: list[str]
    final_output_path: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    web_sources: list[dict[str, Any]] = field(default_factory=list)


def summarize_evidence_sources(
    evidence_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse retrieved chunks into concise, source-level UI records."""
    summaries: dict[str, dict[str, Any]] = {}
    for chunk in evidence_chunks:
        source_id = str(chunk.get("source_id", "")).strip()
        if not source_id:
            continue
        metadata = chunk.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        score = float(chunk.get("score", 0.0))
        matched_sections = metadata.get("matched_sections", [])
        if not isinstance(matched_sections, list):
            matched_sections = []

        summary = summaries.setdefault(
            source_id,
            {
                "source_id": source_id,
                "file_name": str(metadata.get("file_name", "")),
                "score": score,
                "matched_sections": [],
                "quote": str(metadata.get("quote") or chunk.get("text", "")),
            },
        )
        summary["score"] = max(float(summary["score"]), score)
        for section in matched_sections:
            section_name = str(section)
            if section_name not in summary["matched_sections"]:
                summary["matched_sections"].append(section_name)
    return list(summaries.values())


def summarize_web_sources(sources: list[Any]) -> list[dict[str, Any]]:
    """Normalize persisted or in-memory web sources into table-ready rows."""
    rows: list[dict[str, Any]] = []
    for source in sources:
        if isinstance(source, dict):
            value = source
            getter = value.get
        else:
            getter = lambda key, default=None: getattr(source, key, default)

        source_quality = getter("source_quality", "unknown")
        if hasattr(source_quality, "value"):
            source_quality = source_quality.value
        published_date = getter("published_date")
        if hasattr(published_date, "isoformat"):
            published_date = published_date.isoformat()

        rows.append(
            {
                "source_id": str(getter("source_id", "")),
                "agent": str(getter("agent_name", "")),
                "title": str(getter("title", "")),
                "url": str(getter("url", "")),
                "publisher": str(getter("publisher", "") or ""),
                "published_date": str(published_date or ""),
                "quality": str(source_quality),
                "relevance": float(getter("relevance_score", 0.0)),
                "stale": bool(getter("stale", False)),
                "query": str(getter("query", "")),
            }
        )
    return rows


def load_api_key() -> str:
    load_dotenv(ROOT_DIR / ".env")
    import os

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in .env")
    return api_key


def load_system_instruction() -> str:
    if not PROMPT_PATH.is_file():
        raise FileNotFoundError(f"System prompt not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def create_client() -> LLMClient:
    return LLMClient(api_key=load_api_key(), model_name=MODEL_NAME)


def generate_proposal(client: LLMClient, user_idea: str) -> BusinessProposal:
    """Call the shared LLM client with output constrained to BusinessProposal."""
    return client.generate_structured(
        user_idea,
        BusinessProposal,
        temperature=0.4,
        system_instruction=load_system_instruction(),
    )


def proposal_to_markdown(proposal: BusinessProposal) -> str:
    """Render a BusinessProposal as a formatted investor-style Markdown report."""
    lines: list[str] = [
        f"# {proposal.project_name}",
        "",
        f"> **{proposal.tagline}**",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        proposal.executive_summary,
        "",
        "## Pain Points",
        "",
    ]

    for index, pain in enumerate(proposal.pain_points, start=1):
        severity_badge = pain.severity.upper()
        lines.extend(
            [
                f"### {index}. {pain.title} `{severity_badge}`",
                "",
                pain.description,
                "",
            ]
        )

    lines.extend(
        [
            "## Solution",
            "",
            proposal.solution,
            "",
            "## Unique Value Proposition",
            "",
            proposal.unique_value_proposition,
            "",
            "## Target Audiences",
            "",
        ]
    )

    for index, audience in enumerate(proposal.target_audiences, start=1):
        lines.extend(
            [
                f"### {index}. {audience.segment_name}",
                "",
                f"- **Demographics:** {audience.demographics}",
                f"- **Needs:** {audience.needs}",
                f"- **Estimated Size:** {audience.estimated_size}",
                "",
            ]
        )

    market = proposal.market_size
    lines.extend(
        [
            "## Market Size",
            "",
            "| Metric | Estimate |",
            "| --- | --- |",
            f"| **TAM** (Total Addressable Market) | {market.tam} |",
            f"| **SAM** (Serviceable Addressable Market) | {market.sam} |",
            f"| **SOM** (Serviceable Obtainable Market) | {market.som} |",
            f"| **Growth Rate** | {market.growth_rate} |",
            "",
            "## Business Model",
            "",
            proposal.business_model,
            "",
            "## Competitive Landscape",
            "",
            proposal.competitive_landscape,
            "",
            "## Competitive Advantages",
            "",
        ]
    )

    for index, advantage in enumerate(proposal.competitive_advantages, start=1):
        lines.extend(
            [
                f"### {index}. {advantage.advantage}",
                "",
                advantage.description,
                "",
            ]
        )

    financials = proposal.financial_assumptions
    lines.extend(
        [
            "## Go-to-Market Strategy",
            "",
            proposal.go_to_market_strategy,
            "",
            "## Financial Assumptions",
            "",
            "| Assumption | Value |",
            "| --- | --- |",
            f"| Pricing Model | {financials.pricing_model} |",
            f"| Avg. Revenue per Customer | {financials.average_revenue_per_customer} |",
            f"| Gross Margin | {financials.gross_margin} |",
            f"| Customer Acquisition Cost (CAC) | {financials.customer_acquisition_cost} |",
            f"| Monthly Burn Rate | {financials.monthly_burn_rate} |",
            f"| Runway | {financials.runway_months} months |",
            f"| Break-even Timeline | {financials.break_even_timeline} |",
            "",
            "## Funding Ask",
            "",
            proposal.funding_ask,
            "",
            "## Key Metrics",
            "",
        ]
    )

    for metric in proposal.key_metrics:
        lines.append(f"- {metric}")
    lines.append("")

    lines.extend(["## Risks & Mitigations", ""])
    for index, risk in enumerate(proposal.risks_and_mitigations, start=1):
        lines.append(f"{index}. {risk}")
    lines.append("")

    lines.extend(
        [
            "---",
            "",
            f"*Generated by Open Proposal Agent (Phase 1) · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        ]
    )

    return "\n".join(lines)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "business_proposal"


def save_proposal_markdown(proposal: BusinessProposal, output_dir: Path | None = None) -> Path:
    """Convert proposal to Markdown and write to the outputs directory."""
    target_dir = output_dir or OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{_slugify(proposal.project_name)}_{timestamp}.md"
    output_path = target_dir / filename
    output_path.write_text(proposal_to_markdown(proposal), encoding="utf-8")
    return output_path


def run_proposal_pipeline(user_idea: str) -> tuple[BusinessProposal, Path, str]:
    """End-to-end: generate structured proposal and persist Markdown report."""
    client = create_client()
    proposal = generate_proposal(client, user_idea)
    markdown = proposal_to_markdown(proposal)
    output_path = save_proposal_markdown(proposal)
    return proposal, output_path, markdown


def _ensure_run_history_tables() -> None:
    """Create run history tables for local SQLite deployments."""
    Base.metadata.create_all(engine)


def _set_run_status(run_id: str, status: str) -> None:
    """Persist a top-level workflow run status."""
    with get_session() as session:
        update_run_status(session, run_id, status)
        session.commit()


def _get_step_statuses(run_id: str) -> list[dict[str, str]]:
    """Read latest workflow step statuses for Streamlit display."""
    with get_session() as session:
        run = get_run(session, run_id)
        if run is None:
            return []
        return summarize_step_statuses(run)


def _format_run_label(run_id: str, status: str, created_at: datetime) -> str:
    """Build a readable label for a recent run selector or button."""
    created_label = created_at.strftime("%Y-%m-%d %H:%M")
    return f"{created_label} · {status} · {run_id}"


def get_recent_run_summaries(limit: int = 5) -> list[RunSummary]:
    """Return recent persisted workflow runs for the Streamlit sidebar."""
    _ensure_run_history_tables()
    with get_session() as session:
        runs = list_runs(session, limit=limit)
        return [
            RunSummary(
                run_id=run.run_id,
                status=run.status,
                label=_format_run_label(run.run_id, run.status, run.created_at),
            )
            for run in runs
        ]


def _json_preview(value: Any, max_chars: int = 900) -> str:
    """Convert logged JSON-like values into a short human-readable preview."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _extract_final_output_path(run: Any) -> str | None:
    """Read the final exported Markdown path from the latest export node log."""
    node_outputs = sorted(run.node_outputs, key=lambda item: (item.created_at, item.id))
    for node_output in reversed(node_outputs):
        if node_output.node_name != "export":
            continue
        snapshot = node_output.output_snapshot or {}
        output = snapshot.get("output") or {}
        output_path = output.get("output_path")
        if output_path:
            return str(output_path)
    return None


def build_run_detail(run: Any) -> RunDetail:
    """Transform a persisted run record into UI-safe detail data."""
    latest_by_step: dict[str, NodeOutputPreview] = {}
    for node_output in sorted(
        run.node_outputs,
        key=lambda item: (item.created_at, item.id),
    ):
        snapshot = node_output.output_snapshot or {}
        output = snapshot.get("output", snapshot)
        latest_by_step[node_output.node_name] = NodeOutputPreview(
            step=node_output.node_name,
            status=str(snapshot.get("status", "completed")),
            prompt_version=str(snapshot.get("prompt_version", "")),
            output_preview=_json_preview(output),
        )

    step_names = step_names_for_workflow(run.workflow_version)
    ordered_steps = [
        latest_by_step[step_name]
        for step_name in step_names
        if step_name in latest_by_step
    ]
    extra_steps = [
        preview
        for step_name, preview in latest_by_step.items()
        if step_name not in step_names
    ]
    error_messages = [
        f"{error.step_name or 'workflow'}: {error.error_type}: {error.error_message}"
        for error in sorted(run.errors, key=lambda item: (item.created_at, item.id))
    ]

    evidence_chunks: list[dict[str, Any]] = []
    for node_output in sorted(
        run.node_outputs,
        key=lambda item: (item.created_at, item.id),
    ):
        if node_output.node_name != "rag_retrieval":
            continue
        snapshot = node_output.output_snapshot or {}
        output = snapshot.get("output") or {}
        raw_chunks = output.get("evidence_chunks", [])
        if isinstance(raw_chunks, list):
            evidence_chunks = [
                chunk for chunk in raw_chunks if isinstance(chunk, dict)
            ]

    return RunDetail(
        run_id=run.run_id,
        status=run.status,
        input_brief=run.input_brief,
        node_outputs=ordered_steps + extra_steps,
        error_messages=error_messages,
        final_output_path=_extract_final_output_path(run),
        sources=summarize_evidence_sources(evidence_chunks),
        web_sources=summarize_web_sources(list(run.sources)),
    )


def get_run_detail(run_id: str) -> RunDetail | None:
    """Load one persisted run detail for Streamlit display."""
    _ensure_run_history_tables()
    with get_session() as session:
        run = get_run(session, run_id)
        if run is None:
            return None
        return build_run_detail(run)


def run_workflow_pipeline(user_brief: dict[str, str]) -> WorkflowPipelineResult:
    """Run the deterministic LangGraph workflow and return persisted run details.

    Args:
        user_brief: Validated sidebar fields mapped to ``UserBrief`` keys.

    Returns:
        Saved Markdown, run id, and step statuses for UI display.

    Raises:
        ValueError: If the input is incomplete or no Markdown was produced.
    """
    _ensure_run_history_tables()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    with get_session() as session:
        create_run(
            session,
            run_id=run_id,
            session_id="streamlit",
            workflow_version=WORKFLOW_VERSION,
            prompt_version=PROMPT_VERSION,
            model_name=MODEL_NAME,
            input_brief=user_brief,
        )
        update_run_status(session, run_id, "running")
        session.commit()

    graph = build_proposal_workflow_graph(logging_session_factory=get_session)
    result = graph.invoke({"run_id": run_id, "user_brief": user_brief})

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


def run_multi_agent_pipeline(user_brief: dict[str, str]) -> WorkflowPipelineResult:
    """Run and persist the controlled Supervisor-led multi-agent workflow."""
    _ensure_run_history_tables()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    with get_session() as session:
        create_run(
            session,
            run_id=run_id,
            session_id="streamlit",
            workflow_version=MULTI_AGENT_VERSION,
            prompt_version=MULTI_AGENT_PROMPT_VERSION,
            model_name=MODEL_NAME,
            input_brief=user_brief,
        )
        update_run_status(session, run_id, "running")
        session.commit()

    graph = build_multi_agent_workflow_graph(logging_session_factory=get_session)
    result = graph.invoke({"run_id": run_id, "user_brief": user_brief})

    if result.get("missing_info"):
        _set_run_status(run_id, "needs_input")
        raise ValueError("Input incomplete: " + "; ".join(result["missing_info"]))

    markdown = result.get("final_markdown") or result.get("markdown")
    if not markdown:
        _set_run_status(run_id, "failed")
        raise ValueError("Multi-agent workflow finished without a Markdown proposal.")

    _set_run_status(run_id, "completed")
    return WorkflowPipelineResult(
        output_path=Path(result["output_path"]),
        markdown=markdown,
        run_id=run_id,
        step_statuses=_get_step_statuses(run_id),
        sources=summarize_evidence_sources(result.get("evidence_chunks", [])),
        web_sources=summarize_web_sources(result.get("web_sources", [])),
    )


def build_user_idea(
    company_name: str,
    industry: str,
    target_customer: str,
    problem: str,
    solution: str,
    business_model: str,
    geography: str,
    proposal_goal: str,
) -> str:
    """Format sidebar form inputs into a structured prompt for the LLM engine."""
    return f"""
Company Name: {company_name}
Industry: {industry}
Target Customer: {target_customer}
Problem: {problem}
Solution: {solution}
Business Model: {business_model}
Geography: {geography}
Proposal Goal: {proposal_goal}
""".strip()


def build_user_brief(
    company_name: str,
    industry: str,
    target_customer: str,
    problem: str,
    solution: str,
    business_model: str,
    geography: str,
    proposal_goal: str,
) -> dict[str, str]:
    """Map sidebar form inputs to the ``UserBrief`` keys used by the workflow."""
    return {
        "company_or_product_name": company_name,
        "industry": industry,
        "target_customer": target_customer,
        "problem": problem,
        "solution": solution,
        "business_model": business_model,
        "geography": geography,
        "proposal_goal": proposal_goal,
    }


def _render_recent_runs_sidebar(st_module: Any) -> None:
    """Render recent persisted workflow runs in the Streamlit sidebar."""
    st_module.divider()
    st_module.subheader("Recent Runs")
    try:
        recent_runs = get_recent_run_summaries()
    except Exception as exc:
        st_module.caption(f"Run history unavailable: {exc}")
        return

    if not recent_runs:
        st_module.caption("No workflow runs saved yet.")
        return

    for run_summary in recent_runs:
        if st_module.button(
            run_summary.label,
            key=f"recent_run_{run_summary.run_id}",
            use_container_width=True,
        ):
            st_module.session_state["selected_run_id"] = run_summary.run_id


def _render_run_detail(st_module: Any, run_id: str) -> None:
    """Render input, node logs, errors, and export path for one run."""
    detail = get_run_detail(run_id)
    if detail is None:
        st_module.warning(f"Run not found: `{run_id}`")
        return

    st_module.subheader("Run Detail")
    st_module.caption(f"Run ID: `{detail.run_id}` · Status: `{detail.status}`")

    with st_module.expander("Input Brief", expanded=True):
        st_module.json(detail.input_brief or {})

    st_module.markdown("**Node Status and Output Preview**")
    if detail.node_outputs:
        for node_output in detail.node_outputs:
            with st_module.expander(
                f"{node_output.step} · {node_output.status}",
                expanded=False,
            ):
                if node_output.prompt_version:
                    st_module.caption(f"Prompt version: `{node_output.prompt_version}`")
                if node_output.output_preview:
                    st_module.code(node_output.output_preview, language="json")
                else:
                    st_module.caption("No output snapshot saved for this node.")
    else:
        st_module.caption("No node outputs saved for this run.")

    if detail.error_messages:
        st_module.markdown("**Errors**")
        for error_message in detail.error_messages:
            st_module.error(error_message)

    if detail.sources:
        with st_module.expander("Retrieved Sources", expanded=False):
            for source in detail.sources:
                st_module.markdown(f"**`{source['source_id']}` · {source['file_name']}**")
                st_module.caption(
                    f"Relevance: {source['score']:.3f} · Sections: "
                    + ", ".join(source["matched_sections"])
                )
                if source["quote"]:
                    st_module.write(source["quote"][:500])

    if detail.web_sources:
        with st_module.expander("Web Sources", expanded=False):
            st_module.dataframe(
                detail.web_sources,
                use_container_width=True,
                hide_index=True,
            )

    if detail.final_output_path:
        st_module.success(f"Final output path: `{detail.final_output_path}`")
    else:
        st_module.caption("Final output path not saved yet.")

    st_module.divider()


def run_streamlit_app() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="Open Proposal Agent",
        page_icon="📋",
        layout="wide",
    )

    st.title("Open Proposal Agent")
    st.caption("Baseline · Deterministic Workflow · Controlled Multi-Agent")

    with st.sidebar:
        st.header("Business Idea Input")
        run_mode = st.radio(
            "Run Mode",
            ["Baseline", "Workflow", "Multi-Agent"],
            index=0,
            help=(
                "Baseline: single-agent prompt. "
                "Workflow: deterministic LangGraph pipeline "
                "(validate → plan → write → assemble → critique → revise → export). "
                "Multi-Agent: Supervisor → Research → Strategy → Finance → "
                "RAG retrieval → Writer → Critic → Revision."
            ),
        )
        company_name = st.text_input("Company Name", placeholder="e.g. MediQuick AI")
        industry = st.text_input("Industry", placeholder="e.g. Healthcare IT")
        target_customer = st.text_input(
            "Target Customer", placeholder="e.g. General Practitioners in urban areas"
        )
        problem = st.text_area(
            "Problem",
            placeholder="Describe the core pain point your customers face.",
            height=100,
        )
        solution = st.text_area(
            "Solution",
            placeholder="Describe your product or service and how it solves the problem.",
            height=100,
        )
        business_model = st.text_input(
            "Business Model", placeholder="e.g. SaaS (Monthly subscription per doctor)"
        )
        geography = st.text_input("Geography", placeholder="e.g. United States")
        proposal_goal = st.text_input(
            "Proposal Goal",
            placeholder="e.g. Seed funding pitch, accelerator application, internal validation",
        )
        generate_clicked = st.button("Generate Proposal", type="primary", use_container_width=True)
        _render_recent_runs_sidebar(st)

    if generate_clicked:
        required_fields = {
            "Company Name": company_name,
            "Industry": industry,
            "Target Customer": target_customer,
            "Problem": problem,
            "Solution": solution,
            "Business Model": business_model,
            "Geography": geography,
            "Proposal Goal": proposal_goal,
        }
        missing = [label for label, value in required_fields.items() if not value.strip()]
        if missing:
            st.error(f"Please fill in all fields. Missing: {', '.join(missing)}")
        else:
            try:
                if run_mode in {"Workflow", "Multi-Agent"}:
                    user_brief = build_user_brief(
                        company_name=company_name.strip(),
                        industry=industry.strip(),
                        target_customer=target_customer.strip(),
                        problem=problem.strip(),
                        solution=solution.strip(),
                        business_model=business_model.strip(),
                        geography=geography.strip(),
                        proposal_goal=proposal_goal.strip(),
                    )
                    if run_mode == "Multi-Agent":
                        spinner_text = (
                            "Running controlled multi-agent workflow… "
                            "This may take 60–180 seconds."
                        )
                        pipeline = run_multi_agent_pipeline
                    else:
                        spinner_text = (
                            "Running deterministic workflow… "
                            "This may take 30–90 seconds."
                        )
                        pipeline = run_workflow_pipeline
                    with st.spinner(spinner_text):
                        workflow_result = pipeline(user_brief)
                    st.session_state.pop("proposal", None)
                    st.session_state["markdown"] = workflow_result.markdown
                    st.session_state["output_path"] = str(workflow_result.output_path)
                    st.session_state["download_name"] = workflow_result.output_path.name
                    st.session_state["workflow_run_id"] = workflow_result.run_id
                    st.session_state["workflow_step_statuses"] = (
                        workflow_result.step_statuses
                    )
                    st.session_state["workflow_sources"] = workflow_result.sources
                    st.session_state["workflow_web_sources"] = (
                        workflow_result.web_sources
                    )
                    st.session_state["selected_run_id"] = workflow_result.run_id
                else:
                    user_idea = build_user_idea(
                        company_name=company_name.strip(),
                        industry=industry.strip(),
                        target_customer=target_customer.strip(),
                        problem=problem.strip(),
                        solution=solution.strip(),
                        business_model=business_model.strip(),
                        geography=geography.strip(),
                        proposal_goal=proposal_goal.strip(),
                    )
                    with st.spinner("Generating investor-grade proposal… This may take 20–40 seconds."):
                        proposal, output_path, markdown = run_proposal_pipeline(user_idea)
                    st.session_state["proposal"] = proposal
                    st.session_state["markdown"] = markdown
                    st.session_state["output_path"] = str(output_path)
                    st.session_state["download_name"] = output_path.name
                    st.session_state.pop("workflow_run_id", None)
                    st.session_state.pop("workflow_step_statuses", None)
                    st.session_state.pop("workflow_sources", None)
                    st.session_state.pop("workflow_web_sources", None)
            except Exception as exc:
                st.error(f"Generation failed: {exc}")

    selected_run_id = st.session_state.get("selected_run_id")
    if selected_run_id:
        _render_run_detail(st, selected_run_id)

    if "markdown" in st.session_state:
        st.success(f"Report saved to `{st.session_state['output_path']}`")
        if "workflow_run_id" in st.session_state:
            st.caption(f"Workflow run_id: `{st.session_state['workflow_run_id']}`")
            step_statuses = st.session_state.get("workflow_step_statuses", [])
            if step_statuses:
                st.subheader("Workflow Steps")
                for step_status in step_statuses:
                    st.write(
                        f"- `{step_status['step']}`: {step_status['status']}"
                    )
            sources = st.session_state.get("workflow_sources", [])
            if sources:
                st.subheader("Sources")
                for source in sources:
                    with st.expander(
                        f"{source['file_name']} · {source['source_id']}",
                        expanded=False,
                    ):
                        st.caption(
                            f"Relevance: {source['score']:.3f} · Sections: "
                            + ", ".join(source["matched_sections"])
                        )
                        if source["quote"]:
                            st.write(source["quote"][:500])
            web_sources = st.session_state.get("workflow_web_sources", [])
            if web_sources:
                st.subheader("Web Sources")
                st.dataframe(
                    web_sources,
                    use_container_width=True,
                    hide_index=True,
                )
        st.download_button(
            label="Download Markdown",
            data=st.session_state["markdown"],
            file_name=st.session_state.get("download_name", "business_proposal.md"),
            mime="text/markdown",
            type="primary",
        )
        st.divider()
        st.markdown(st.session_state["markdown"])
    else:
        st.info("Fill in the sidebar form and click **Generate Proposal** to get started.")


if __name__ == "__main__":
    run_streamlit_app()
