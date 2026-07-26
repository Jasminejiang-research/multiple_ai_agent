"""Knowledge-base indexing and section-aware retrieval for proposal writing."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from rag.evidence_filter import filter_evidence
from rag.index import DEFAULT_COLLECTION_NAME, VectorIndex, add_documents, build_index
from rag.loaders import LoadedDocument, load_document
from rag.retriever import EvidenceChunk, retrieve, rewrite_query

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_BASE_DIR = ROOT_DIR / "knowledge_base"
SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
_TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


class LocalHashEmbeddingFunction:
    """Create deterministic local embeddings without network or API calls."""

    def __init__(self, dimensions: int = 384) -> None:
        """Configure the fixed number of hashed token dimensions."""
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8.")
        self.dimensions = dimensions

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        """Embed documents using normalized hashed token-frequency vectors."""
        return [self._embed_text(text) for text in input]

    def embed_query(self, input: Sequence[str]) -> list[list[float]]:
        """Embed retrieval queries in the same deterministic vector space."""
        return self(input)

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _TOKEN_PATTERN.findall(text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            position = int.from_bytes(digest[:8], "big") % self.dimensions
            vector[position] += 1.0

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            return vector
        return [value / magnitude for value in vector]

    @staticmethod
    def name() -> str:
        """Return the stable Chroma embedding-function name."""
        return "open-proposal-local-hash"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "LocalHashEmbeddingFunction":
        """Recreate the embedding function from serialized Chroma config."""
        return LocalHashEmbeddingFunction(dimensions=int(config.get("dimensions", 384)))

    def get_config(self) -> dict[str, Any]:
        """Return the serializable Chroma configuration."""
        return {"dimensions": self.dimensions}

    def is_legacy(self) -> bool:
        """Use Chroma's direct callable path without global registration."""
        return True


def load_knowledge_base_documents(
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
) -> list[LoadedDocument]:
    """Load every supported seed document beneath the knowledge-base folders."""
    root = Path(knowledge_base_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge base directory does not exist: {root}")

    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and path.name.casefold() != "readme.md"
    )
    documents = [load_document(path) for path in paths]
    if not documents:
        raise ValueError(f"Knowledge base contains no supported documents: {root}")
    return documents


def build_knowledge_base_index(
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
) -> VectorIndex:
    """Build an ephemeral Chroma index from local proposal knowledge."""
    index = build_index(
        collection_name=DEFAULT_COLLECTION_NAME,
        embedding_function=LocalHashEmbeddingFunction(),
    )
    add_documents(index, load_knowledge_base_documents(knowledge_base_dir))
    return index


def retrieve_writer_evidence(
    user_brief: str | Mapping[str, Any] | BaseModel,
    sections: Sequence[str],
    *,
    index: VectorIndex | None = None,
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    top_k: int = 3,
    min_score: float = 0.2,
) -> list[EvidenceChunk]:
    """Retrieve and merge filtered evidence for each proposal section.

    Repeated chunks are returned once, with every matching proposal section
    recorded in ``metadata["matched_sections"]``.
    """
    active_index = index or build_knowledge_base_index(knowledge_base_dir)
    merged: list[EvidenceChunk] = []
    position_by_identity: dict[tuple[str, str], int] = {}

    for section in sections:
        query = rewrite_query(user_brief, section)
        matches = filter_evidence(
            retrieve(query, top_k, index=active_index),
            min_score=min_score,
        )
        for match in matches:
            metadata = dict(match.metadata)
            chunk_id = str(metadata.get("chunk_id", "")).strip()
            identity = (match.source_id, chunk_id or match.text)
            if identity in position_by_identity:
                existing = merged[position_by_identity[identity]]
                matched_sections = list(
                    existing.metadata.get("matched_sections", [])
                )
                if section not in matched_sections:
                    matched_sections.append(section)
                    existing.metadata["matched_sections"] = matched_sections
                continue

            metadata["matched_sections"] = [section]
            position_by_identity[identity] = len(merged)
            merged.append(
                EvidenceChunk(
                    source_id=match.source_id,
                    text=match.text,
                    score=match.score,
                    metadata=metadata,
                )
            )

    return merged
