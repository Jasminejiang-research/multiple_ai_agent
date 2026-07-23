"""Traceable query rewriting and vector retrieval for the RAG pipeline."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rag.index import VectorIndex


class EvidenceChunk(BaseModel):
    """One relevant, source-traceable chunk returned by the vector index."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _serialize_user_brief(user_brief: str | Mapping[str, Any] | BaseModel) -> str:
    """Turn supported brief inputs into stable text suitable for retrieval."""
    if isinstance(user_brief, str):
        serialized = user_brief.strip()
    else:
        if isinstance(user_brief, BaseModel):
            brief_data: Mapping[str, Any] = user_brief.model_dump(mode="json")
        elif isinstance(user_brief, Mapping):
            brief_data = user_brief
        else:
            raise TypeError("user_brief must be a string, mapping, or Pydantic model.")

        serialized = json.dumps(
            dict(brief_data),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    if not serialized:
        raise ValueError("user_brief must not be blank.")
    return serialized


def rewrite_query(
    user_brief: str | Mapping[str, Any] | BaseModel,
    section: str,
) -> str:
    """Combine the proposal brief and target section into a focused RAG query."""
    if not isinstance(section, str):
        raise TypeError("section must be a string.")

    normalized_section = section.strip()
    if not normalized_section:
        raise ValueError("section must not be blank.")

    serialized_brief = _serialize_user_brief(user_brief)
    return (
        f"Proposal section: {normalized_section}\n"
        f"Relevant user brief: {serialized_brief}"
    )


def _distance_to_score(distance: Any) -> float:
    """Convert Chroma's non-negative distance into a bounded relevance score."""
    numeric_distance = max(float(distance), 0.0)
    return 1.0 / (1.0 + numeric_distance)


def _first_query_batch(result: Mapping[str, Any], key: str) -> list[Any]:
    """Return the first result list from Chroma's batched query response."""
    batches = result.get(key)
    if not batches:
        return []
    first_batch = batches[0]
    return list(first_batch) if first_batch is not None else []


def retrieve(
    query: str,
    top_k: int = 5,
    *,
    index: VectorIndex,
    query_embedding: Sequence[float] | None = None,
) -> list[EvidenceChunk]:
    """Retrieve the top matching chunks while preserving source metadata.

    ``query_embedding`` is optional and primarily supports callers that manage
    embeddings themselves. When omitted, Chroma embeds ``query`` using the
    collection's configured embedding function.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string.")

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank.")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer.")
    if not isinstance(index, VectorIndex):
        raise TypeError("index must be a VectorIndex.")

    query_options: dict[str, Any] = {
        "n_results": top_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if query_embedding is None:
        query_options["query_texts"] = [normalized_query]
    else:
        embedding = list(query_embedding)
        if not embedding:
            raise ValueError("query_embedding must not be empty.")
        query_options["query_embeddings"] = [embedding]

    result = index.collection.query(**query_options)
    ids = _first_query_batch(result, "ids")
    documents = _first_query_batch(result, "documents")
    metadatas = _first_query_batch(result, "metadatas")
    distances = _first_query_batch(result, "distances")

    chunks: list[EvidenceChunk] = []
    for position, text in enumerate(documents):
        metadata = (
            dict(metadatas[position])
            if position < len(metadatas) and metadatas[position] is not None
            else {}
        )
        if position < len(ids):
            metadata.setdefault("chunk_id", str(ids[position]))

        source_id = str(metadata.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("Retrieved chunks must include a non-blank source_id.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Retrieved chunks must include non-blank text.")
        if position >= len(distances):
            raise ValueError("Retrieved chunks must include a distance score.")

        metadata["source_id"] = source_id
        metadata.setdefault("quote", text)
        chunks.append(
            EvidenceChunk(
                source_id=source_id,
                text=text,
                score=_distance_to_score(distances[position]),
                metadata=metadata,
            )
        )

    return chunks
