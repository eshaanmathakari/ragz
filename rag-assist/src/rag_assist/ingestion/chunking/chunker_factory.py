"""Chunker factory for routing documents to appropriate chunking strategy."""

import structlog

from rag_assist.ingestion.chunking.base_chunker import BaseChunker
from rag_assist.ingestion.chunking.docx_chunker import DOCXChunker
from rag_assist.ingestion.chunking.pdf_chunker import PDFChunker
from rag_assist.ingestion.chunking.pptx_chunker import PPTXChunker
from rag_assist.ingestion.models import DocumentType, ParsedDocument, TextChunk

logger = structlog.get_logger(__name__)


class ChunkerFactory:
    """Factory for creating and managing document chunkers.

    Routes documents to appropriate chunker based on document type.
    """

    def __init__(
        self,
        target_tokens: int | None = None,
        max_tokens: int | None = None,
        include_speaker_notes: bool = True,
        include_tables: bool = True,
    ):
        """Initialize chunker factory.

        Args:
            target_tokens: Target chunk size in tokens.
            max_tokens: Maximum chunk size in tokens.
            include_speaker_notes: Include speaker notes in PPTX chunks.
            include_tables: Include tables in all chunk types.
        """
        common_kwargs = {
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
        }

        self._chunkers: dict[DocumentType, BaseChunker] = {
            DocumentType.PDF: PDFChunker(
                include_tables=include_tables,
                **common_kwargs,
            ),
            DocumentType.PPTX: PPTXChunker(
                include_speaker_notes=include_speaker_notes,
                include_tables=include_tables,
                **common_kwargs,
            ),
            DocumentType.DOCX: DOCXChunker(
                include_tables=include_tables,
                **common_kwargs,
            ),
        }

    def get_chunker(self, document: ParsedDocument) -> BaseChunker | None:
        """Get appropriate chunker for document.

        Args:
            document: Parsed document.

        Returns:
            Chunker instance or None if no suitable chunker.
        """
        doc_type = document.metadata.file_type

        if doc_type not in self._chunkers:
            logger.warning(f"No chunker available for document type: {doc_type}")
            return None

        return self._chunkers[doc_type]

    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk a parsed document.

        Args:
            document: Parsed document to chunk.

        Returns:
            List of text chunks.
        """
        chunker = self.get_chunker(document)
        if not chunker:
            return []

        return chunker.chunk(document)

    def chunk_batch(self, documents: list[ParsedDocument]) -> list[TextChunk]:
        """Chunk multiple documents.

        Args:
            documents: List of parsed documents.

        Returns:
            Combined list of text chunks from all documents.
        """
        all_chunks = []

        for document in documents:
            try:
                chunks = self.chunk(document)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(
                    f"Failed to chunk document {document.metadata.filename}: {str(e)}"
                )

        logger.info(
            f"Chunked {len(documents)} documents into {len(all_chunks)} chunks"
        )
        return all_chunks
