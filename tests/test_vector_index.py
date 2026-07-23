"""Tests for the local Chroma vector index."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rag.index import add_documents, build_index, load_index, persist_index
from rag.loaders import LoadedDocument


class VectorIndexTests(unittest.TestCase):
    """Exercise index creation, document storage, and persistence."""

    def test_index_can_be_created_and_persisted(self) -> None:
        """A local index should retain documents and traceable metadata."""
        # Chroma can release its HNSW files just after context cleanup on Windows.
        with TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            index = build_index(
                collection_name="test_proposal_knowledge",
                embedding_function=None,
            )
            document = LoadedDocument(
                page_content="A traceable market fact.",
                metadata={
                    "source_id": "market-report-001",
                    "file_name": "market_report.md",
                    "page_number": 3,
                },
            )

            chunk_ids = add_documents(
                index,
                [document],
                embeddings=[[1.0, 0.0, 0.0]],
            )
            persisted = persist_index(index, Path(directory) / "chroma")
            loaded = load_index(
                Path(directory) / "chroma",
                collection_name="test_proposal_knowledge",
                embedding_function=None,
            )
            records = loaded.collection.get(
                ids=chunk_ids,
                include=["documents", "metadatas"],
            )

            self.assertEqual(len(index), 1)
            self.assertEqual(len(persisted), 1)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(records["documents"], ["A traceable market fact."])
            self.assertEqual(records["metadatas"][0]["source_id"], "market-report-001")
            self.assertEqual(records["metadatas"][0]["chunk_id"], chunk_ids[0])
            self.assertEqual(records["metadatas"][0]["page_number"], 3)


if __name__ == "__main__":
    unittest.main()
