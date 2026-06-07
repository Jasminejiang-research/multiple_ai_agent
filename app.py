"""Open Proposal Agent — Phase 1 single-agent baseline."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas.proposal_schema import BusinessProposal

ROOT_DIR = Path(__file__).resolve().parent
PROMPT_PATH = ROOT_DIR / "prompts" / "single_agent_proposal.md"
OUTPUT_DIR = ROOT_DIR / "outputs"
MODEL_NAME = "gemini-2.5-flash"


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


def run_proposal_pipeline(user_idea: str) -> tuple[BusinessProposal, Path]:
    """End-to-end: generate structured proposal and persist Markdown report."""
    client = create_client()
    proposal = generate_proposal(client, user_idea)
    output_path = save_proposal_markdown(proposal)
    return proposal, output_path


if __name__ == "__main__":
    test_idea = """
Company Name: MediQuick AI
Industry: Healthcare IT
Target Customer: General Practitioners in urban areas
Problem: Doctors spend 3+ hours daily on administrative paperwork instead of patient care.
Solution: An AI-powered voice assistant that listens to doctor-patient consultations and automatically drafts compliant electronic health records (EHR).
Business Model: SaaS (Monthly subscription per doctor)
Geography: United States
""".strip()

    print("Generating investor-grade business proposal via Gemini...\n")
    proposal, report_path = run_proposal_pipeline(test_idea)

    print("=== Parsed BusinessProposal (Pydantic) ===")
    print(proposal.model_dump_json(indent=2))
    print(f"\nMarkdown report saved to: {report_path}")
