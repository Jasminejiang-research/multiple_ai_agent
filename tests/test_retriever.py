"""Tests for traceable RAG query rewriting and retrieval."""

from __future__ import annotations

import unittest

from rag.index import add_documents, build_index
from rag.loaders import LoadedDocument
from rag.retriever import EvidenceChunk, retrieve, rewrite_query


class RetrieverTests(unittest.TestCase):
    """Exercise query construction and EvidenceChunk conversion."""

    def test_rewrite_query_includes_brief_and_section(self) -> None:
        query = rewrite_query(
            {
                "project_name": "Circular Packaging",
                "target_customer": "European food manufacturers",
            },
            "Market Opportunity",
        )

        self.assertIn("Market Opportunity", query)
        self.assertIn("Circular Packaging", query)
        self.assertIn("European food manufacturers", query)

    def test_query_returns_traceable_evidence_chunk(self) -> None:
        index = build_index(
            collection_name="test_retriever",
            embedding_function=None,
        )
        add_documents(
            index,
            [
                LoadedDocument(
                    page_content="Reusable packaging demand is growing.",
                    metadata={
                        "source_id": "industry-report-001",
                        "file_name": "industry_report.md",
                        "page_number": 4,
                    },
                ),
                LoadedDocument(
                    page_content="This chunk is less relevant.",
                    metadata={
                        "source_id": "example-proposal-001",
                        "file_name": "example.md",
                    },
                ),
            ],
            embeddings=[
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
        )

        chunks = retrieve(
            "packaging market demand",
            1,
            index=index,
            query_embedding=[1.0, 0.0, 0.0],
        )

        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0], EvidenceChunk)
        self.assertEqual(chunks[0].source_id, "industry-report-001")
        self.assertEqual(
            chunks[0].text,
            "Reusable packaging demand is growing.",
        )
        self.assertEqual(chunks[0].score, 1.0)
        self.assertEqual(chunks[0].metadata["file_name"], "industry_report.md")
        self.assertEqual(chunks[0].metadata["page_number"], 4)
        self.assertIn("chunk_id", chunks[0].metadata)
        self.assertEqual(chunks[0].metadata["quote"], chunks[0].text)


if __name__ == "__main__":
    unittest.main()
