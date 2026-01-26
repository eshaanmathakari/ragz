"""PDF chunker using page-based chunking strategy."""

import structlog

from rag_assist.ingestion.chunking.base_chunker import BaseChunker
from rag_assist.ingestion.models import (
    ChunkMetadata,
    DocumentType,
    PageContent,
    ParsedDocument,
    TextChunk,
)

logger = structlog.get_logger(__name__)


class PDFChunker(BaseChunker):
    """Page-based chunker for PDF documents.

    Strategy:
    - Each page becomes one or more chunks
    - Split pages that exceed token limit
    - Preserve page number for citations
    - Attempt to detect section boundaries
    """

    def __init__(
        self,
        include_tables: bool = True,
        respect_page_boundaries: bool = True,
        **kwargs,
    ):
        """Initialize PDF chunker.

        Args:
            include_tables: Include table content in chunks.
            respect_page_boundaries: Keep chunks within page boundaries.
            **kwargs: Arguments passed to BaseChunker.
        """
        super().__init__(**kwargs)
        self.include_tables = include_tables
        self.respect_page_boundaries = respect_page_boundaries

    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk PDF document by pages.

        Args:
            document: Parsed PDF document.

        Returns:
            List of text chunks.
        """
        if document.metadata.file_type != DocumentType.PDF:
            logger.warning(
                f"PDFChunker received non-PDF document: {document.metadata.file_type}"
            )
            return []

        if not document.content:
            return []

        document_id = self.generate_document_id(document)
        base_metadata = self.create_base_metadata(document, document_id)
        chunks: list[TextChunk] = []
        chunk_index = 0

        # Track section context across pages
        current_section = ""

        for page in document.content:
            if not isinstance(page, PageContent):
                continue

            # Detect section from page (look for heading-like text)
            detected_section = self._detect_section(page)
            if detected_section:
                current_section = detected_section

            page_chunks = self._chunk_page(
                page=page,
                base_metadata=base_metadata,
                chunk_index=chunk_index,
                section_title=current_section,
            )

            chunks.extend(page_chunks)
            chunk_index += len(page_chunks)

        self.log_chunking_result(document, chunks)
        return chunks

    def _chunk_page(
        self,
        page: PageContent,
        base_metadata: dict,
        chunk_index: int,
        section_title: str,
    ) -> list[TextChunk]:
        """Chunk a single page.

        Args:
            page: Page content.
            base_metadata: Base metadata dictionary.
            chunk_index: Starting chunk index.
            section_title: Current section title.

        Returns:
            List of chunks from this page.
        """
        # Build page text
        page_text = self._build_page_text(page)

        if not page_text.strip():
            return []

        # Check if page fits in one chunk
        token_count = self.count_tokens(page_text)

        if token_count <= self.max_tokens:
            # Single chunk for page
            return [
                self._create_chunk(
                    text=page_text,
                    page=page,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index,
                    position="only",
                    token_count=token_count,
                    section_title=section_title,
                )
            ]

        # Page too large, split into multiple chunks
        if self.respect_page_boundaries:
            # Split by paragraphs first, then by tokens
            text_parts = self._split_page_content(page_text)
        else:
            text_parts = self.split_text_by_tokens(page_text, self.max_tokens)

        chunks = []
        for i, part in enumerate(text_parts):
            position = self.determine_position(i, len(text_parts))
            chunks.append(
                self._create_chunk(
                    text=part,
                    page=page,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index + i,
                    position=position,
                    token_count=self.count_tokens(part),
                    section_title=section_title,
                )
            )

        return chunks

    def _build_page_text(self, page: PageContent) -> str:
        """Build full text representation of page.

        Args:
            page: Page content.

        Returns:
            Combined text from page.
        """
        parts = [page.text]

        # Add tables
        if self.include_tables and page.tables:
            for table in page.tables:
                table_text = self._format_table(table)
                if table_text:
                    parts.append(f"\n{table_text}")

        return "\n".join(parts)

    def _split_page_content(self, text: str) -> list[str]:
        """Split page content intelligently by paragraphs.

        Args:
            text: Page text.

        Returns:
            List of text chunks.
        """
        # Split by double newlines (paragraphs)
        paragraphs = text.split("\n\n")

        chunks = []
        current_chunk = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If single paragraph exceeds limit, split it
            if para_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                    current_tokens = 0

                # Split large paragraph
                sub_chunks = self.split_text_by_tokens(para, self.max_tokens)
                chunks.extend(sub_chunks)
                continue

            # Check if adding paragraph exceeds limit
            if current_tokens + para_tokens > self.max_tokens:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
                current_tokens = para_tokens
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
                current_tokens += para_tokens

        # Add remaining content
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _detect_section(self, page: PageContent) -> str:
        """Detect section title from page content.

        Args:
            page: Page content.

        Returns:
            Detected section title or empty string.
        """
        # Look for heading-like text blocks
        for block in page.text_blocks:
            if block.is_heading or (block.font_size and block.font_size > 14):
                # Likely a heading
                text = block.text.strip()
                if len(text) < 100 and text:  # Headings are usually short
                    return text

        return ""

    def _format_table(self, table: list[list[str]]) -> str:
        """Format table as text.

        Args:
            table: Table data as list of rows.

        Returns:
            Formatted table text.
        """
        if not table:
            return ""

        lines = ["[Table]"]
        for row in table:
            row_text = " | ".join(cell for cell in row)
            lines.append(row_text)
        lines.append("[/Table]")

        return "\n".join(lines)

    def _create_chunk(
        self,
        text: str,
        page: PageContent,
        base_metadata: dict,
        chunk_index: int,
        position: str,
        token_count: int,
        section_title: str,
    ) -> TextChunk:
        """Create a text chunk from page content.

        Args:
            text: Chunk text.
            page: Source page.
            base_metadata: Base metadata dictionary.
            chunk_index: Chunk index in document.
            position: Position in page (if split).
            token_count: Token count.
            section_title: Current section title.

        Returns:
            TextChunk with metadata.
        """
        metadata = ChunkMetadata(
            chunk_id=self.generate_chunk_id(),
            document_id=base_metadata["document_id"],
            filename=base_metadata["filename"],
            file_type=base_metadata["file_type"],
            s3_uri=base_metadata["s3_uri"],
            module_name=base_metadata["module_name"],
            folder_path=base_metadata["folder_path"],
            week_number=base_metadata["week_number"],
            page_number=page.page_number,
            section_title=section_title,
            heading_hierarchy=[section_title] if section_title else [],
            chunk_index=chunk_index,
            position_in_section=position,
            content_type="page",
            char_count=len(text),
            token_count=token_count,
            extraction_method=page.extraction_method,
            extraction_confidence=page.confidence,
            content_hash=self.compute_content_hash(text),
        )

        return TextChunk(text=text, metadata=metadata)
