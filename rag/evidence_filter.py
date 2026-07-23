"""Deterministic quality filtering for retrieved evidence chunks."""

from __future__ import annotations

from collections.abc import Iterable
from math import isfinite

from rag.retriever import EvidenceChunk


def _chunk_identity(chunk: EvidenceChunk) -> tuple[str, ...]:
    """Return a stable identity, preferring the retriever's chunk ID."""
    chunk_id = str(chunk.metadata.get("chunk_id", "")).strip()
    if chunk_id:
        return ("chunk_id", chunk_id)
    return ("source_text", chunk.source_id, chunk.text.strip())


def filter_evidence(
    chunks: Iterable[EvidenceChunk],
    min_score: float,
) -> list[EvidenceChunk]:
    """Keep non-blank, sufficiently relevant, unique evidence in input order."""
    if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
        raise TypeError("min_score must be a number.")

    normalized_min_score = float(min_score)
    if not isfinite(normalized_min_score) or not 0.0 <= normalized_min_score <= 1.0:
        raise ValueError("min_score must be between 0.0 and 1.0.")

    filtered: list[EvidenceChunk] = []
    seen: set[tuple[str, ...]] = set()
    for chunk in chunks:
        if not isinstance(chunk, EvidenceChunk):
            raise TypeError("chunks must contain only EvidenceChunk instances.")
        if not chunk.text.strip() or chunk.score < normalized_min_score:
            continue

        identity = _chunk_identity(chunk)
        if identity in seen:
            continue

        seen.add(identity)
        filtered.append(chunk)

    return filtered
