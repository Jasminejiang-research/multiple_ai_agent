"""Open Proposal Agent — Phase 1 single-agent baseline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.proposal_schema import BusinessProposal
from storage.db import Base, engine, get_session
from storage.repositories import create_run, get_run, update_run_status
from workflow.graph import build_proposal_workflow_graph
from workflow.logging import (
    PROMPT_VERSION,
    WORKFLOW_VERSION,
    summarize_step_statuses,
)

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


def create_client() -> genai.Client:
    return genai.Client(api_key=load_api_key())


def generate_proposal(client: genai.Client, user_idea: str) -> BusinessProposal:
    """Call Gemini with structured output constrained to BusinessProposal."""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_idea,
        config=types.GenerateContentConfig(
            system_instruction=load_system_instruction(),
            response_mime_type="application/json",
            response_schema=BusinessProposal,
            temperature=0.4,
        ),
    )

    if response.parsed is not None:
        if isinstance(response.parsed, BusinessProposal):
            return response.parsed
        return BusinessProposal.model_validate(response.parsed)

    if not response.text:
        raise ValueError("Gemini returned an empty response.")

    return BusinessProposal.model_validate_json(response.text)


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


def run_streamlit_app() -> None:
    import streamlit as st

    st.set_page_config(
        page_title="Open Proposal Agent",
        page_icon="📋",
        layout="wide",
    )

    st.title("Open Proposal Agent")
    st.caption("Phase 1 · Single-Agent Baseline · Investor-Grade Business Proposals")

    with st.sidebar:
        st.header("Business Idea Input")
        run_mode = st.radio(
            "Run Mode",
            ["Baseline", "Workflow"],
            index=0,
            help=(
                "Baseline: single-agent prompt. "
                "Workflow: deterministic LangGraph pipeline "
                "(validate → plan → write → assemble → critique → revise → export)."
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
                if run_mode == "Workflow":
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
                    with st.spinner("Running deterministic workflow… This may take 30–90 seconds."):
                        workflow_result = run_workflow_pipeline(user_brief)
                    st.session_state.pop("proposal", None)
                    st.session_state["markdown"] = workflow_result.markdown
                    st.session_state["output_path"] = str(workflow_result.output_path)
                    st.session_state["download_name"] = workflow_result.output_path.name
                    st.session_state["workflow_run_id"] = workflow_result.run_id
                    st.session_state["workflow_step_statuses"] = (
                        workflow_result.step_statuses
                    )
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
            except Exception as exc:
                st.error(f"Generation failed: {exc}")

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
