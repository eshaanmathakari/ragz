"""PowerPoint chunker using slide-based chunking strategy."""

import structlog

from rag_assist.ingestion.chunking.base_chunker import BaseChunker
from rag_assist.ingestion.models import (
    ChunkMetadata,
    DocumentType,
    ParsedDocument,
    SlideContent,
    TextChunk,
)

logger = structlog.get_logger(__name__)


class PPTXChunker(BaseChunker):
    """Slide-based chunker for PowerPoint documents.

    Strategy:
    - Each slide becomes one chunk (preserves slide context)
    - If slide exceeds token limit, split into multiple chunks
    - Include speaker notes as additional context
    """

    def __init__(
        self,
        include_speaker_notes: bool = True,
        include_tables: bool = True,
        **kwargs,
    ):
        """Initialize PPTX chunker.

        Args:
            include_speaker_notes: Include speaker notes in chunk text.
            include_tables: Include table content in chunk text.
            **kwargs: Arguments passed to BaseChunker.
        """
        super().__init__(**kwargs)
        self.include_speaker_notes = include_speaker_notes
        self.include_tables = include_tables

    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk PowerPoint document by slides.

        Args:
            document: Parsed PowerPoint document.

        Returns:
            List of text chunks, typically one per slide.
        """
        if document.metadata.file_type != DocumentType.PPTX:
            logger.warning(
                f"PPTXChunker received non-PPTX document: {document.metadata.file_type}"
            )
            return []

        if not document.content:
            return []

        document_id = self.generate_document_id(document)
        base_metadata = self.create_base_metadata(document, document_id)
        chunks: list[TextChunk] = []
        chunk_index = 0

        for slide in document.content:
            if not isinstance(slide, SlideContent):
                continue

            slide_chunks = self._chunk_slide(
                slide=slide,
                base_metadata=base_metadata,
                chunk_index=chunk_index,
            )

            chunks.extend(slide_chunks)
            chunk_index += len(slide_chunks)

        self.log_chunking_result(document, chunks)
        return chunks

    def _chunk_slide(
        self,
        slide: SlideContent,
        base_metadata: dict,
        chunk_index: int,
    ) -> list[TextChunk]:
        """Chunk a single slide.

        Args:
            slide: Slide content.
            base_metadata: Base metadata dictionary.
            chunk_index: Starting chunk index.

        Returns:
            List of chunks from this slide.
        """
        # Build slide text
        slide_text = self._build_slide_text(slide)

        if not slide_text.strip():
            return []

        # Check if slide fits in one chunk
        token_count = self.count_tokens(slide_text)

        if token_count <= self.max_tokens:
            # Single chunk for slide
            return [
                self._create_chunk(
                    text=slide_text,
                    slide=slide,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index,
                    position="only",
                    token_count=token_count,
                )
            ]

        # Slide too large, split into multiple chunks
        text_parts = self.split_text_by_tokens(slide_text, self.max_tokens)
        chunks = []

        for i, part in enumerate(text_parts):
            position = self.determine_position(i, len(text_parts))
            chunks.append(
                self._create_chunk(
                    text=part,
                    slide=slide,
                    base_metadata=base_metadata,
                    chunk_index=chunk_index + i,
                    position=position,
                    token_count=self.count_tokens(part),
                )
            )

        return chunks

    def _build_slide_text(self, slide: SlideContent) -> str:
        """Build full text representation of slide.

        Args:
            slide: Slide content.

        Returns:
            Combined text from slide.
        """
        parts = []

        # Title
        if slide.title:
            parts.append(f"# {slide.title}")

        # Body text
        for block in slide.body_text:
            if block.text.strip():
                # Add indentation for list items
                prefix = "  " * block.level + "• " if block.level > 0 else ""
                parts.append(f"{prefix}{block.text}")

        # Tables
        if self.include_tables and slide.tables:
            for table in slide.tables:
                table_text = self._format_table(table)
                if table_text:
                    parts.append(f"\n{table_text}")

        # Speaker notes
        if self.include_speaker_notes and slide.speaker_notes:
            parts.append(f"\n[Speaker Notes: {slide.speaker_notes}]")

        return "\n".join(parts)

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
        slide: SlideContent,
        base_metadata: dict,
        chunk_index: int,
        position: str,
        token_count: int,
    ) -> TextChunk:
        """Create a text chunk from slide content.

        Args:
            text: Chunk text.
            slide: Source slide.
            base_metadata: Base metadata dictionary.
            chunk_index: Chunk index in document.
            position: Position in slide (if split).
            token_count: Token count.

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
            slide_number=slide.slide_number,
            section_title=slide.title,
            heading_hierarchy=[slide.title] if slide.title else [],
            chunk_index=chunk_index,
            position_in_section=position,
            content_type="slide",
            char_count=len(text),
            token_count=token_count,
            extraction_method=base_metadata["extraction_method"],
            content_hash=self.compute_content_hash(text),
        )

        return TextChunk(text=text, metadata=metadata)
