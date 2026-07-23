"""Tests for deterministic evidence filtering."""

from __future__ import annotations

import unittest

from rag.evidence_filter import filter_evidence
from rag.retriever import EvidenceChunk


def _chunk(
    *,
    source_id: str,
    text: str,
    score: float,
    chunk_id: str | None = None,
    file_name: str | None = None,
) -> EvidenceChunk:
    metadata = {}
    if chunk_id is not None:
        metadata["chunk_id"] = chunk_id
    if file_name is not None:
        metadata["file_name"] = file_name
    return EvidenceChunk.model_construct(
        source_id=source_id,
        text=text,
        score=score,
        metadata=metadata,
    )


class EvidenceFilterTests(unittest.TestCase):
    """Exercise content, score, duplicate, and metadata filtering rules."""

    def test_filters_empty_low_score_and_duplicate_chunks(self) -> None:
        kept = _chunk(
            source_id="report-001",
            text="The addressable market is expanding.",
            score=0.8,
            chunk_id="chunk-001",
            file_name="market_report.pdf",
        )
        chunks = [
            _chunk(source_id="report-001", text="   ", score=0.9, chunk_id="empty"),
            _chunk(
                source_id="report-002",
                text="Weakly related evidence.",
                score=0.49,
                chunk_id="low",
            ),
            kept,
            _chunk(
                source_id="report-001",
                text="Duplicate retrieval.",
                score=0.95,
                chunk_id="chunk-001",
            ),
        ]

        result = filter_evidence(chunks, min_score=0.5)

        self.assertEqual(result, [kept])
        self.assertIs(result[0], kept)
        self.assertEqual(
            result[0].metadata,
            {"chunk_id": "chunk-001", "file_name": "market_report.pdf"},
        )

    def test_deduplicates_missing_chunk_ids_by_source_and_text(self) -> None:
        first = _chunk(
            source_id="upload-001",
            text="Customer interviews identify long setup times.",
            score=0.7,
        )
        duplicate = _chunk(
            source_id="upload-001",
            text="Customer interviews identify long setup times.",
            score=0.9,
        )
        other_source = _chunk(
            source_id="upload-002",
            text="Customer interviews identify long setup times.",
            score=0.9,
        )

        result = filter_evidence([first, duplicate, other_source], min_score=0.7)

        self.assertEqual(result, [first, other_source])

    def test_rejects_min_score_outside_supported_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0.0 and 1.0"):
            filter_evidence([], min_score=1.1)


if __name__ == "__main__":
    unittest.main()
