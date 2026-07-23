"""Chroma-backed vector index lifecycle helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

if TYPE_CHECKING:
    from rag.loaders import LoadedDocument


DEFAULT_COLLECTION_NAME = "proposal_knowledge"
_DEFAULT_EMBEDDING_FUNCTION = object()
_CHROMA_METADATA_TYPES = (str, int, float, bool)


@dataclass(slots=True)
class VectorIndex:
    """A Chroma client and collection plus their persistence location."""

    client: Any
    collection: Any
    collection_name: str
    persist_directory: Path | None = None

    def __len__(self) -> int:
        """Return the number of indexed document chunks."""
        return int(self.collection.count())


def _load_chromadb() -> Any:
    """Import Chroma with an actionable error when dependencies are missing."""
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "Chroma is required for vector indexing. Install project dependencies "
            "from requirements.txt."
        ) from exc
    return chromadb


def _collection_options(
    embedding_function: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build collection options without overriding Chroma's default embedder."""
    options: dict[str, Any] = {}
    if embedding_function is not _DEFAULT_EMBEDDING_FUNCTION:
        options["embedding_function"] = embedding_function
    if metadata:
        options["metadata"] = dict(metadata)
    return options


def build_index(
    persist_directory: str | PathLike[str] | None = None,
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_function: Any = _DEFAULT_EMBEDDING_FUNCTION,
) -> VectorIndex:
    """Create or open an in-memory or local persistent Chroma collection."""
    chromadb = _load_chromadb()

    resolved_directory: Path | None = None
    if persist_directory is None:
        client = chromadb.EphemeralClient()
    else:
        resolved_directory = Path(persist_directory).expanduser().resolve()
        resolved_directory.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(resolved_directory))

    collection = client.get_or_create_collection(
        name=collection_name,
        **_collection_options(
            embedding_function,
            metadata={"purpose": "proposal_knowledge_base"},
        ),
    )
    return VectorIndex(
        client=client,
        collection=collection,
        collection_name=collection_name,
        persist_directory=resolved_directory,
    )


def _stable_chunk_id(source_id: str, text: str) -> str:
    """Create an idempotent chunk ID from its source and content."""
    digest = hashlib.sha256(f"{source_id}\0{text}".encode("utf-8")).hexdigest()
    return f"chunk_{digest[:24]}"


def _chroma_metadata(metadata: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    """Convert arbitrary loader metadata into Chroma-supported scalar values."""
    normalized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        normalized_key = str(key)
        if isinstance(value, _CHROMA_METADATA_TYPES):
            normalized[normalized_key] = value
        else:
            normalized[normalized_key] = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
    return normalized


def add_documents(
    index: VectorIndex,
    documents: Iterable[LoadedDocument],
    *,
    embeddings: Sequence[Sequence[float]] | None = None,
) -> list[str]:
    """Upsert loaded documents while retaining source and chunk metadata."""
    loaded_documents = list(documents)
    if not loaded_documents:
        return []

    texts: list[str] = []
    metadatas: list[dict[str, str | int | float | bool]] = []
    chunk_ids: list[str] = []

    for document in loaded_documents:
        text = document.page_content
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Indexed documents must contain non-blank page_content.")

        metadata = dict(document.metadata)
        source_id = str(metadata.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("Indexed documents must include a non-blank source_id.")

        explicit_chunk_id = str(metadata.get("chunk_id", "")).strip()
        chunk_id = explicit_chunk_id or _stable_chunk_id(source_id, text)
        metadata["source_id"] = source_id
        metadata["chunk_id"] = chunk_id

        texts.append(text)
        metadatas.append(_chroma_metadata(metadata))
        chunk_ids.append(chunk_id)

    if len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("A document batch must not contain duplicate chunk IDs.")

    upsert_options: dict[str, Any] = {
        "ids": chunk_ids,
        "documents": texts,
        "metadatas": metadatas,
    }
    if embeddings is not None:
        supplied_embeddings = list(embeddings)
        if len(supplied_embeddings) != len(loaded_documents):
            raise ValueError("embeddings must contain one vector per document.")
        upsert_options["embeddings"] = supplied_embeddings

    index.collection.upsert(**upsert_options)
    return chunk_ids


def _flush_legacy_client(index: VectorIndex) -> None:
    """Flush clients from Chroma releases that still expose persist()."""
    persist = getattr(index.client, "persist", None)
    if callable(persist):
        persist()


def persist_index(
    index: VectorIndex,
    persist_directory: str | PathLike[str] | None = None,
) -> VectorIndex:
    """Persist an index, copying an ephemeral index when a directory is supplied."""
    target_directory = (
        Path(persist_directory).expanduser().resolve()
        if persist_directory is not None
        else index.persist_directory
    )
    if target_directory is None:
        raise ValueError(
            "persist_directory is required when persisting an in-memory index."
        )

    if index.persist_directory == target_directory:
        _flush_legacy_client(index)
        return index

    embedding_function = getattr(
        index.collection,
        "_embedding_function",
        _DEFAULT_EMBEDDING_FUNCTION,
    )
    persisted = build_index(
        target_directory,
        collection_name=index.collection_name,
        embedding_function=embedding_function,
    )
    records = index.collection.get(
        include=["documents", "metadatas", "embeddings"],
    )
    record_ids = records.get("ids") or []
    if record_ids:
        persisted.collection.upsert(
            ids=record_ids,
            documents=records.get("documents"),
            metadatas=records.get("metadatas"),
            embeddings=records.get("embeddings"),
        )
    _flush_legacy_client(persisted)
    return persisted


def load_index(
    persist_directory: str | PathLike[str],
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_function: Any = _DEFAULT_EMBEDDING_FUNCTION,
) -> VectorIndex:
    """Load an existing persistent Chroma collection from disk."""
    directory = Path(persist_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Vector index directory does not exist: {directory}")

    chromadb = _load_chromadb()
    client = chromadb.PersistentClient(path=str(directory))
    collection = client.get_collection(
        name=collection_name,
        **_collection_options(embedding_function),
    )
    return VectorIndex(
        client=client,
        collection=collection,
        collection_name=collection_name,
        persist_directory=directory,
    )
