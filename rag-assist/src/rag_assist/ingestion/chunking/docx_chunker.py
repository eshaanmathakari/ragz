"""Word document chunker using heading-based chunking strategy."""

import structlog

from rag_assist.ingestion.chunking.base_chunker import BaseChunker
from rag_assist.ingestion.models import (
    ChunkMetadata,
    DocumentType,
    ParsedDocument,
    SectionContent,
    TextChunk,
)

logger = structlog.get_logger(__name__)


class DOCXChunker(BaseChunker):
    """Heading-based chunker for Word documents.

    Strategy:
    - Chunk by heading sections
    - Preserve heading hierarchy for context
    - Split sections that exceed token limit
    """

    def __init__(
        self,
        include_tables: bool = True,
        preserve_hierarchy: bool = True,
        **kwargs,
    ):
        """Initialize DOCX chunker.

        Args:
            include_tables: Include table content in chunks.
            preserve_hierarchy: Preserve heading hierarchy in metadata.
            **kwargs: Arguments passed to BaseChunker.
        """
        super().__init__(**kwargs)
        self.include_tables = include_tables
        self.preserve_hierarchy = preserve_hierarchy

    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk Word document by sections.

        Args:
            document: Parsed Word document.

        Returns:
            List of text chunks.
        """
        if document.metadata.file_type != DocumentType.DOCX:
            logger.warning(
                f"DOCXChunker received non-DOCX document: {document.metadata.file_type}"
            )
            return []

        if not document.content:
            return []

        document_id = self.generate_document_id(document)
        base_metadata = self.create_base_metadata(document, document_id)
        chunks: list[TextChunk] = []
        chunk_index = 0

        # Track heading hierarchy
        heading_stack: list[tuple[int, str]] = []  # (level, title)

        for section in document.content:
            if not isinstance(section, SectionContent):
                continue

            # Update heading hierarchy
            if section.heading:
                heading_stack = self._update_hierarchy(
                    heading_stack, section.heading_level, section.heading
                )

            # Get current hierarchy as list
            hierarchy = [title for _, title in heading_stack]

            section_chunks = self._chunk_section(
                section=section,
                base_metadata=base_metadata,
                chunk_index=chunk_index,
                heading_hierarchy=hierarchy,
            )

            chunks.extend(section_chunks)
            chunk_index += len(section_chunks)

        self.log_chunking_result(document, chunks)
        return chunks

    def _update_hierarchy(
        self,
        stack: list[tuple[int, str]],
        level: int,
        title: str,
    ) -> list[tuple[int, str]]:
        """Update heading hierarchy stack.

        Args:
            stack: Current heading stack.
            level: New heading level.
            title: New heading title.

        Returns:
            Updated heading stack.
        """
        if not self.preserve_hierarchy:
            return [(level, title)]

        # Remove all headings at same or lower level
        while stack and stack[-1][0] >= level:
            stack.pop()

        # Add new heading
        stack.append((level, title))
        return stack

    def _chunk_section(
        self,
        section: SectionContent,
        base_metadata: dict,
        chunk_index: int,
        heading_hierarchy: list[str],
    ) -> list[TextChunk]:
        """Chunk a single section.

        Args:
            section: Section content.
            base_metadata: Base metadata dictionary.
            chunk_index: Starting chunk index.
            heading_hierarchy: Current heading hierarchy.

        Returns:
            List of chunks from this section.
        """
        # Build section text
        section_text = self._build_section_text(section)

        if not section_text.strip():
            return []

        # Check if section fits in one chunk
        token_count = self.count_tokens(section_text)

        if token_count <= self.max_tokens:
            # Single chunk for section
            return [
                self._create_chunk(
                    text=section_text,
                    section=section,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index,
                    position="only",
                    token_count=token_count,
                    heading_hierarchy=heading_hierarchy,
                )
            ]

        # Section too large, split into multiple chunks
        text_parts = self._split_section_content(section_text)
        chunks = []

        for i, part in enumerate(text_parts):
            position = self.determine_position(i, len(text_parts))
            chunks.append(
                self._create_chunk(
                    text=part,
                    section=section,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index + i,
                    position=position,
                    token_count=self.count_tokens(part),
                    heading_hierarchy=heading_hierarchy,
                )
            )

        return chunks

    def _build_section_text(self, section: SectionContent) -> str:
        """Build full text representation of section.

        Args:
            section: Section content.

        Returns:
            Combined text from section.
        """
        parts = []

        # Heading
        if section.heading:
            heading_prefix = "#" * max(1, section.heading_level)
            parts.append(f"{heading_prefix} {section.heading}")

        # Content blocks
        for block in section.content:
            if block.text.strip():
                # Add indentation for list items
                if block.block_type == "list_item":
                    prefix = "  " * block.level + "• "
                    parts.append(f"{prefix}{block.text}")
                elif block.block_type == "quote":
                    parts.append(f"> {block.text}")
                else:
                    parts.append(block.text)

        # Tables
        if self.include_tables and section.tables:
            for table in section.tables:
                table_text = self._format_table(table)
                if table_text:
                    parts.append(f"\n{table_text}")

        return "\n\n".join(parts)

    def _split_section_content(self, text: str) -> list[str]:
        """Split section content intelligently.

        Args:
            text: Section text.

        Returns:
            List of text chunks.
        """
        # Split by paragraphs (double newlines)
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
        section: SectionContent,
        base_metadata: dict,
        chunk_index: int,
        position: str,
        token_count: int,
        heading_hierarchy: list[str],
    ) -> TextChunk:
        """Create a text chunk from section content.

        Args:
            text: Chunk text.
            section: Source section.
            base_metadata: Base metadata dictionary.
            chunk_index: Chunk index in document.
            position: Position in section (if split).
            token_count: Token count.
            heading_hierarchy: Heading hierarchy path.

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
            section_title=section.heading,
            heading_hierarchy=heading_hierarchy.copy(),
            chunk_index=chunk_index,
            position_in_section=position,
            content_type="section",
            char_count=len(text),
            token_count=token_count,
            extraction_method=base_metadata["extraction_method"],
            content_hash=self.compute_content_hash(text),
        )

        return TextChunk(text=text, metadata=metadata)
