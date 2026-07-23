"""Local document loaders for the RAG knowledge base."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from os import PathLike
from pathlib import Path


MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
TXT_SUFFIXES = frozenset({".txt"})
PDF_SUFFIXES = frozenset({".pdf"})


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Text content and traceable metadata for one loaded source document."""

    page_content: str
    metadata: dict[str, str]

    @property
    def source_id(self) -> str:
        """Return the stable source identifier stored in the metadata."""
        return self.metadata["source_id"]

    @property
    def text(self) -> str:
        """Expose a neutral text alias for callers that do not use page_content."""
        return self.page_content


def _read_text_document(
    file_path: str | PathLike[str],
    *,
    allowed_suffixes: frozenset[str],
    file_type: str,
    encoding: str,
    source_id: str | None,
) -> LoadedDocument:
    """Read a local text document and attach its source metadata."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Document does not exist or is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix not in allowed_suffixes:
        expected = ", ".join(sorted(allowed_suffixes))
        raise ValueError(
            f"Expected a {file_type} document with extension {expected}; got {suffix or '(none)'}."
        )

    raw_content = path.read_bytes()
    page_content = raw_content.decode(encoding)
    resolved_source_id = _resolve_source_id(raw_content, source_id)
    resolved_path = path.resolve()

    return LoadedDocument(
        page_content=page_content,
        metadata={
            "source_id": resolved_source_id,
            "source": str(resolved_path),
            "file_name": path.name,
            "file_type": file_type,
            "file_extension": suffix,
        },
    )


def _resolve_source_id(raw_content: bytes, source_id: str | None) -> str:
    """Return an explicit source ID or a stable content-derived one."""
    if source_id is not None:
        normalized_source_id = source_id.strip()
        if not normalized_source_id:
            raise ValueError("source_id must not be blank.")
        return normalized_source_id

    digest = hashlib.sha256(raw_content).hexdigest()
    return f"source_{digest[:24]}"


def load_markdown(
    file_path: str | PathLike[str],
    *,
    encoding: str = "utf-8-sig",
    source_id: str | None = None,
) -> LoadedDocument:
    """Load one Markdown file while preserving source metadata."""
    return _read_text_document(
        file_path,
        allowed_suffixes=MARKDOWN_SUFFIXES,
        file_type="markdown",
        encoding=encoding,
        source_id=source_id,
    )


def load_txt(
    file_path: str | PathLike[str],
    *,
    encoding: str = "utf-8-sig",
    source_id: str | None = None,
) -> LoadedDocument:
    """Load one plain-text file while preserving source metadata."""
    return _read_text_document(
        file_path,
        allowed_suffixes=TXT_SUFFIXES,
        file_type="text",
        encoding=encoding,
        source_id=source_id,
    )


def load_pdf(
    file_path: str | PathLike[str],
    *,
    source_id: str | None = None,
) -> LoadedDocument:
    """Reserve the PDF loader API for a later implementation."""
    del file_path, source_id
    raise NotImplementedError("PDF document loading is not implemented yet.")


def load_document(
    file_path: str | PathLike[str],
    *,
    encoding: str = "utf-8-sig",
    source_id: str | None = None,
) -> LoadedDocument:
    """Load a supported document by its extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return load_markdown(file_path, encoding=encoding, source_id=source_id)
    if suffix in TXT_SUFFIXES:
        return load_txt(file_path, encoding=encoding, source_id=source_id)
    if suffix in PDF_SUFFIXES:
        return load_pdf(file_path, source_id=source_id)

    supported = ", ".join(sorted(MARKDOWN_SUFFIXES | TXT_SUFFIXES | PDF_SUFFIXES))
    raise ValueError(
        f"Unsupported document extension {suffix or '(none)'}; expected one of: {supported}."
    )
