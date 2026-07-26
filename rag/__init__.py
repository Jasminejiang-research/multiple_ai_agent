"""Retrieval-augmented generation helpers."""

from rag.citation_checker import (
    CitationCoverageReport,
    CitationFailure,
    CitationValidationError,
    ClaimCitationCheck,
    EvidenceGap,
    check_citations,
    check_claim_has_source,
    citation_coverage_score,
    collect_proposal_citation_failures,
    extract_key_claims,
    extract_structured_claims,
    validate_proposal_citations,
)
from rag.evidence_filter import filter_evidence
from rag.knowledge_base import (
    LocalHashEmbeddingFunction,
    build_knowledge_base_index,
    load_knowledge_base_documents,
    retrieve_writer_evidence,
)
from rag.loaders import (
    LoadedDocument,
    load_document,
    load_markdown,
    load_pdf,
    load_txt,
)
from rag.retriever import EvidenceChunk, retrieve, rewrite_query

__all__ = [
    "CitationCoverageReport",
    "CitationFailure",
    "CitationValidationError",
    "ClaimCitationCheck",
    "EvidenceGap",
    "EvidenceChunk",
    "LocalHashEmbeddingFunction",
    "LoadedDocument",
    "check_citations",
    "check_claim_has_source",
    "citation_coverage_score",
    "collect_proposal_citation_failures",
    "extract_key_claims",
    "extract_structured_claims",
    "filter_evidence",
    "build_knowledge_base_index",
    "load_knowledge_base_documents",
    "load_document",
    "load_markdown",
    "load_pdf",
    "load_txt",
    "retrieve",
    "retrieve_writer_evidence",
    "rewrite_query",
    "validate_proposal_citations",
]
