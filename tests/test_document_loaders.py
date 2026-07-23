"""Tests for local RAG document loaders."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rag.loaders import load_document, load_markdown, load_pdf, load_txt


class DocumentLoaderTests(unittest.TestCase):
    """Exercise supported text loaders and the reserved PDF API."""

    def test_load_markdown_preserves_content_and_source_metadata(self) -> None:
        """A Markdown file should remain traceable after it is loaded."""
        with TemporaryDirectory() as directory:
            markdown_path = Path(directory) / "market_notes.md"
            markdown_path.write_text(
                "# Market Notes\n\nEvidence-backed market context.",
                encoding="utf-8",
                newline="\n",
            )

            document = load_markdown(markdown_path)

            self.assertEqual(
                document.page_content,
                "# Market Notes\n\nEvidence-backed market context.",
            )
            self.assertEqual(document.text, document.page_content)
            self.assertTrue(document.source_id.startswith("source_"))
            self.assertEqual(
                document.metadata,
                {
                    "source_id": document.source_id,
                    "source": str(markdown_path.resolve()),
                    "file_name": "market_notes.md",
                    "file_type": "markdown",
                    "file_extension": ".md",
                },
            )

    def test_load_txt_supports_an_explicit_source_id(self) -> None:
        """A caller-provided source ID should be retained for citation mapping."""
        with TemporaryDirectory() as directory:
            txt_path = Path(directory) / "interview.txt"
            txt_path.write_text(
                "Customer interview notes.",
                encoding="utf-8",
                newline="\n",
            )

            document = load_txt(txt_path, source_id="interview-001")

            self.assertEqual(document.page_content, "Customer interview notes.")
            self.assertEqual(document.source_id, "interview-001")
            self.assertEqual(document.metadata["file_type"], "text")

    def test_load_document_dispatches_by_extension(self) -> None:
        """The generic entry point should choose the Markdown loader."""
        with TemporaryDirectory() as directory:
            markdown_path = Path(directory) / "framework.markdown"
            markdown_path.write_text("# Framework", encoding="utf-8", newline="\n")

            document = load_document(markdown_path)

            self.assertEqual(document.metadata["file_type"], "markdown")

    def test_pdf_loader_is_an_explicit_placeholder(self) -> None:
        """PDF loading should fail clearly until its later implementation."""
        with self.assertRaisesRegex(NotImplementedError, "not implemented"):
            load_pdf("report.pdf")


if __name__ == "__main__":
    unittest.main()
