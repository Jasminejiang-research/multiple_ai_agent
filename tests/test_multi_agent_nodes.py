"""Focused tests for multi-agent evidence degradation and prompt budgeting."""

from __future__ import annotations

import unittest

from rag.retriever import EvidenceChunk
from workflow.multi_agent_nodes import (
    MAX_EVIDENCE_CHARS_PER_CHUNK,
    MAX_EVIDENCE_CHUNKS,
    build_deterministic_supervisor_plan,
    rag_retrieval_node,
)


class RagRetrievalNodeTests(unittest.TestCase):
    """Verify that absent or excessive RAG evidence is handled deterministically."""

    def test_empty_rag_with_web_sources_uses_web_only_mode(self) -> None:
        """No knowledge-base match no longer stops a run with Web evidence."""
        result = rag_retrieval_node(
            {
                "user_brief": {"company_or_product_name": "Example"},
                "web_sources": [{"source_id": "web-1"}],
            },
            evidence_provider=lambda brief, sections: [],
        )

        self.assertEqual(result["evidence_chunks"], [])
        self.assertEqual(result["evidence_mode"], "web_only")
        self.assertTrue(result["low_confidence_required"])

    def test_evidence_is_ranked_and_shortened_with_explicit_metadata(self) -> None:
        """The RAG packet stays within count/text budgets without hidden trimming."""
        chunks = [
            EvidenceChunk(
                source_id=f"source-{index}",
                text="x" * (MAX_EVIDENCE_CHARS_PER_CHUNK + 100),
                score=index / (MAX_EVIDENCE_CHUNKS + 1),
                metadata={"chunk_id": f"chunk-{index}"},
            )
            for index in range(MAX_EVIDENCE_CHUNKS + 1)
        ]

        result = rag_retrieval_node(
            {"user_brief": {"company_or_product_name": "Example"}},
            evidence_provider=lambda brief, sections: chunks,
        )

        self.assertEqual(len(result["evidence_chunks"]), MAX_EVIDENCE_CHUNKS)
        self.assertTrue(result["evidence_was_budget_limited"])
        self.assertTrue(
            all(
                chunk["metadata"]["prompt_budget_truncated"]
                for chunk in result["evidence_chunks"]
            )
        )
        self.assertNotIn("source-0", {
            chunk["source_id"] for chunk in result["evidence_chunks"]
        })


class DeterministicSupervisorTests(unittest.TestCase):
    """The fixed five-role route must not depend on a model response."""

    def test_plan_contains_one_bounded_task_per_required_role(self) -> None:
        plan = build_deterministic_supervisor_plan()

        self.assertEqual(
            plan.selected_agents,
            ["research", "strategy", "finance", "writer", "critic"],
        )
        self.assertEqual(len(plan.tasks), 5)
        self.assertTrue(
            all(len(task.input_requirements) <= 8 for task in plan.tasks)
        )


if __name__ == "__main__":
    unittest.main()
