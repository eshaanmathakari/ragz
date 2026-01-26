"""Unit tests for chunking strategies."""

import pytest

from rag_assist.ingestion.chunking.pptx_chunker import PPTXChunker
from rag_assist.ingestion.chunking.pdf_chunker import PDFChunker
from rag_assist.ingestion.models import DocumentType


class TestPPTXChunker:
    """Tests for PPTX chunker."""

    def test_chunk_creates_one_chunk_per_slide(self, sample_pptx_content):
        """Each slide should become a separate chunk."""
        chunker = PPTXChunker(max_tokens=500)
        chunks = chunker.chunk(sample_pptx_content)

        assert len(chunks) == 3
        assert all(c.metadata.slide_number is not None for c in chunks)

    def test_chunk_includes_slide_title(self, sample_pptx_content):
        """Chunk text should include slide title."""
        chunker = PPTXChunker(max_tokens=500, include_title=True)
        chunks = chunker.chunk(sample_pptx_content)

        # First slide has title "Introduction to ML"
        assert "Introduction to ML" in chunks[0].text

    def test_chunk_includes_speaker_notes(self, sample_pptx_content):
        """Chunk should include speaker notes when enabled."""
        chunker = PPTXChunker(max_tokens=500, include_notes=True)
        chunks = chunker.chunk(sample_pptx_content)

        # First slide has speaker notes
        assert "Speaker notes for slide 1" in chunks[0].text

    def test_chunk_preserves_metadata(self, sample_pptx_content):
        """Chunk metadata should be properly set."""
        chunker = PPTXChunker()
        chunks = chunker.chunk(sample_pptx_content)

        assert chunks[0].metadata.filename == "test_presentation.pptx"
        assert chunks[0].metadata.file_type == "pptx"
        assert chunks[0].metadata.week_number == 1  # Extracted from "week 1" in path

    def test_empty_document_returns_no_chunks(self):
        """Empty document should return empty list."""
        from rag_assist.ingestion.models import DocumentMetadata, ParsedDocument

        doc = ParsedDocument(
            content=[],
            metadata=DocumentMetadata(
                filename="empty.pptx",
                file_type=DocumentType.PPTX,
                s3_uri="s3://bucket/empty.pptx",
                file_size=0,
            ),
            raw_text="",
        )

        chunker = PPTXChunker()
        chunks = chunker.chunk(doc)

        assert len(chunks) == 0


class TestPDFChunker:
    """Tests for PDF chunker."""

    def test_chunk_creates_chunks_from_pages(self, sample_pdf_content):
        """Each page should become one or more chunks."""
        chunker = PDFChunker(max_tokens=500)
        chunks = chunker.chunk(sample_pdf_content)

        assert len(chunks) >= 2  # At least one chunk per page
        assert all(c.metadata.page_number is not None for c in chunks)

    def test_chunk_detects_section_headings(self, sample_pdf_content):
        """Section titles should be detected from headings."""
        chunker = PDFChunker(max_tokens=500)
        chunks = chunker.chunk(sample_pdf_content)

        # First page has heading "Neural Network Architecture"
        assert chunks[0].metadata.section_title == "Neural Network Architecture"

    def test_large_page_splits_into_multiple_chunks(self):
        """Large pages should be split into multiple chunks."""
        from rag_assist.ingestion.models import (
            DocumentMetadata,
            DocumentType,
            PageContent,
            ParsedDocument,
        )

        # Create a page with lots of text
        large_text = "This is a test sentence. " * 500  # ~2500 tokens

        doc = ParsedDocument(
            content=[
                PageContent(
                    page_number=1,
                    text=large_text,
                    text_blocks=[],
                )
            ],
            metadata=DocumentMetadata(
                filename="large.pdf",
                file_type=DocumentType.PDF,
                s3_uri="s3://bucket/large.pdf",
                file_size=10000,
                total_pages=1,
            ),
            raw_text="",
        )

        chunker = PDFChunker(max_tokens=300)
        chunks = chunker.chunk(doc)

        assert len(chunks) > 1  # Should split into multiple chunks

    def test_chunk_includes_content_hash(self, sample_pdf_content):
        """Each chunk should have a content hash."""
        chunker = PDFChunker()
        chunks = chunker.chunk(sample_pdf_content)

        assert all(c.metadata.content_hash is not None for c in chunks)
        assert all(len(c.metadata.content_hash) > 0 for c in chunks)


class TestChunkMetadata:
    """Tests for chunk metadata extraction."""

    def test_week_number_extracted_from_path(self, sample_pptx_content):
        """Week number should be extracted from S3 path."""
        chunker = PPTXChunker()
        chunks = chunker.chunk(sample_pptx_content)

        # Path is "s3://test-bucket/week 1/..."
        assert chunks[0].metadata.week_number == 1

    def test_chunk_id_is_unique(self, sample_pptx_content):
        """Each chunk should have a unique ID."""
        chunker = PPTXChunker()
        chunks = chunker.chunk(sample_pptx_content)

        chunk_ids = [c.metadata.chunk_id for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))  # All unique

    def test_document_id_is_consistent(self, sample_pptx_content):
        """All chunks from same document should share document_id."""
        chunker = PPTXChunker()
        chunks = chunker.chunk(sample_pptx_content)

        document_ids = [c.metadata.document_id for c in chunks]
        assert len(set(document_ids)) == 1  # All same
