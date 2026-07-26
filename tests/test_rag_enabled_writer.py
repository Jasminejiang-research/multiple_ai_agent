"""Integration tests for knowledge-base retrieval before proposal writing."""

from __future__ import annotations

from pathlib import Path

from agents.writer import WriterAgent
from rag.citation_checker import check_citations
from rag.knowledge_base import (
    build_knowledge_base_index,
    load_knowledge_base_documents,
    retrieve_writer_evidence,
)
from rag.retriever import EvidenceChunk
from schemas.agent_outputs import (
    FinanceAssumptions,
    ResearchAnalysis,
    StrategyAnalysis,
    WriterInput,
)
from schemas.workflow import (
    PROPOSAL_SECTION_FIELD_NAMES,
    PROPOSAL_SECTION_TITLES,
    ProposalDraft,
)


class FakeWriterLLM:
    """Return a deterministic evidence-grounded proposal for the Writer test."""

    def __init__(self, response: str) -> None:
        """Store the response and prompts for later assertions."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the Writer prompt and return the prepared proposal JSON."""
        self.prompts.append(prompt)
        return self.response


def _writer_input(evidence_chunks: list[EvidenceChunk]) -> WriterInput:
    """Build the three analysis packets plus retrieved Writer evidence."""
    finding = {
        "topic": "Subscription analytics",
        "finding": "The brief indicates a need for clearer subscription economics.",
        "rationale": "The proposed product helps teams understand recurring revenue.",
        "confidence": "medium",
    }
    insight = {
        "topic": "Evidence-led finance",
        "recommendation": "Use transparent unit-economics assumptions in the proposal.",
        "rationale": "This makes financial reasoning reviewable before external use.",
        "confidence": "medium",
    }
    assumption = {
        "topic": "Subscription revenue",
        "assumption": "Recurring subscriptions could fund the product if demand is validated.",
        "rationale": "The supplied business model is a SaaS subscription.",
        "confidence": "low",
        "needs_validation": ["Pricing and retention tests"],
    }
    return WriterInput(
        research_analysis=ResearchAnalysis(
            analysis_summary="Research remains cautious until evidence is applied.",
            market_trends=[finding],
            customer_notes=[finding],
            competitor_assumptions=[finding],
            unsupported_claims=[],
            needs_human_review=[],
        ),
        strategy_analysis=StrategyAnalysis(
            analysis_summary="The strategy uses transparent, testable assumptions.",
            value_proposition=[insight],
            business_model_logic=[insight],
            gtm_strategy=[insight],
            moat_hypotheses=[insight],
            unsupported_market_data=[],
            needs_human_review=[],
        ),
        finance_assumptions=FinanceAssumptions(
            analysis_summary="Financial logic is preliminary and evidence-sensitive.",
            revenue_assumptions=[assumption],
            cost_assumptions=[assumption],
            unit_economics_assumptions=[assumption],
            break_even_discussion=(
                "Break-even depends on validated pricing, retention, acquisition, "
                "and delivery-cost assumptions."
            ),
            assumption_notice="All financial figures are assumptions, not forecasts.",
            unsupported_financial_claims=[],
            needs_human_review=[],
        ),
        evidence_chunks=evidence_chunks,
    )


def _proposal_json(source_id: str) -> str:
    """Build a full proposal with one source-sensitive, cited key fact."""
    cited_claim = (
        f"Gross margin is a financial benchmark for unit economics [{source_id}]."
    )
    proposal_data: dict[str, object] = {
        "title": "Subscription Analytics Proposal"
    }
    for title, field_name in zip(
        PROPOSAL_SECTION_TITLES,
        PROPOSAL_SECTION_FIELD_NAMES,
        strict=True,
    ):
        is_financial_section = title == "Financial Assumptions"
        proposal_data[field_name] = {
            "title": title,
            "content": (
                cited_claim
                if is_financial_section
                else (
                    f"This {title} section stays within the supplied analysis "
                    "and labels uncertain statements for later validation."
                )
            ),
            "key_claims": (
                [
                    {
                        "text": cited_claim,
                        "claim_type": "financial_benchmark",
                        "evidence_status": "sourced_fact",
                        "source_ids": [source_id],
                        "content_anchor": cited_claim,
                    }
                ]
                if is_financial_section
                else []
            ),
            "source_ids": [source_id] if is_financial_section else [],
            "confidence": "medium",
        }
    return ProposalDraft.model_validate(proposal_data).model_dump_json()


def test_seed_knowledge_base_can_be_retrieved_with_traceable_sources(
    tmp_path: Path,
) -> None:
    """Retrieved evidence should ground Writer claims with full citation coverage."""
    knowledge_base = tmp_path / "knowledge_base"
    frameworks = knowledge_base / "business_frameworks"
    frameworks.mkdir(parents=True)
    source_path = frameworks / "unit_economics.md"
    source_path.write_text(
        "# Unit Economics\nTrack CAC, LTV, gross margin, and payback period.",
        encoding="utf-8",
    )

    documents = load_knowledge_base_documents(knowledge_base)
    index = build_knowledge_base_index(knowledge_base)
    chunks = retrieve_writer_evidence(
        {
            "company_or_product_name": "Subscription Analytics",
            "business_model": "SaaS subscription",
        },
        ["Financial Assumptions"],
        index=index,
        top_k=1,
        min_score=0.0,
    )

    assert len(documents) == 1
    assert len(chunks) == 1
    assert chunks[0].source_id == documents[0].source_id
    assert chunks[0].metadata["file_name"] == source_path.name
    assert chunks[0].metadata["chunk_id"]
    assert chunks[0].metadata["quote"] == chunks[0].text
    assert chunks[0].metadata["matched_sections"] == ["Financial Assumptions"]

    retrieved_source_ids = {chunk.source_id for chunk in chunks}
    writer_llm = FakeWriterLLM(_proposal_json(chunks[0].source_id))
    proposal = WriterAgent(llm_client=writer_llm).run(_writer_input(chunks))
    financial_section = proposal.financial_assumptions

    assert len(writer_llm.prompts) == 1
    assert chunks[0].source_id in writer_llm.prompts[0]
    assert f"[{chunks[0].source_id}]" in financial_section.content
    assert set(financial_section.source_ids).issubset(retrieved_source_ids)

    citation_report = check_citations(financial_section)

    assert citation_report.required_claim_count == 1
    assert citation_report.cited_claim_count == 1
    assert citation_report.coverage_score == 1.0
