"""Base chunker interface for content chunking strategies."""

import hashlib
import re
import uuid
from abc import ABC, abstractmethod

import structlog
import tiktoken

from rag_assist.config.settings import get_settings
from rag_assist.ingestion.models import ChunkMetadata, ParsedDocument, TextChunk

logger = structlog.get_logger(__name__)


class BaseChunker(ABC):
    """Abstract base class for document chunkers."""

    def __init__(
        self,
        target_tokens: int | None = None,
        max_tokens: int | None = None,
        min_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ):
        """Initialize chunker with configuration.

        Args:
            target_tokens: Target chunk size in tokens.
            max_tokens: Maximum chunk size in tokens.
            min_tokens: Minimum chunk size in tokens.
            overlap_tokens: Overlap between consecutive chunks.
        """
        settings = get_settings()

        self.target_tokens = target_tokens or settings.chunking.size_tokens
        self.max_tokens = max_tokens or settings.chunking.max_size_tokens
        self.min_tokens = min_tokens or settings.chunking.min_size_tokens
        self.overlap_tokens = overlap_tokens or settings.chunking.overlap_tokens

        # Initialize tokenizer (cl100k_base for Claude/GPT-4 compatibility)
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens.
        """
        if not text:
            return 0
        return len(self._tokenizer.encode(text))

    def estimate_tokens(self, text: str) -> int:
        """Quick token estimation without encoding.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count (chars / 4 is rough approximation).
        """
        if not text:
            return 0
        return len(text) // 4

    @abstractmethod
    def chunk(self, document: ParsedDocument) -> list[TextChunk]:
        """Chunk a parsed document into text chunks.

        Args:
            document: Parsed document to chunk.

        Returns:
            List of text chunks with metadata.
        """
        pass

    def generate_chunk_id(self) -> str:
        """Generate unique chunk ID.

        Returns:
            UUID string.
        """
        return str(uuid.uuid4())

    def generate_document_id(self, document: ParsedDocument) -> str:
        """Generate unique document ID based on content hash.

        Args:
            document: Parsed document.

        Returns:
            Document ID string.
        """
        # Use file path and modification time for uniqueness
        unique_str = f"{document.metadata.file_path}:{document.metadata.modified_at}"
        return hashlib.sha256(unique_str.encode()).hexdigest()[:16]

    def compute_content_hash(self, text: str) -> str:
        """Compute SHA-256 hash of normalized text for deduplication.

        Args:
            text: Text content.

        Returns:
            SHA-256 hash string.
        """
        normalized = self._normalize_for_hash(text)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _normalize_for_hash(self, text: str) -> str:
        """Normalize text for consistent hashing.

        Args:
            text: Text to normalize.

        Returns:
            Normalized text.
        """
        if not text:
            return ""

        # Lowercase
        text = text.lower()

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove punctuation
        text = re.sub(r"[^\w\s]", "", text)

        return text.strip()

    def split_text_by_tokens(
        self,
        text: str,
        max_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> list[str]:
        """Split text into chunks respecting token limits.

        Args:
            text: Text to split.
            max_tokens: Maximum tokens per chunk.
            overlap_tokens: Overlap between chunks.

        Returns:
            List of text chunks.
        """
        max_tokens = max_tokens or self.max_tokens
        overlap_tokens = overlap_tokens or self.overlap_tokens

        if not text:
            return []

        # Tokenize
        tokens = self._tokenizer.encode(text)

        if len(tokens) <= max_tokens:
            return [text]

        chunks = []
        start = 0

        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))

            # Get chunk tokens
            chunk_tokens = tokens[start:end]

            # Decode back to text
            chunk_text = self._tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text.strip())

            # Move start with overlap
            start = end - overlap_tokens

            # Prevent infinite loop
            if start >= len(tokens) - 1:
                break

        return chunks

    def determine_position(self, index: int, total: int) -> str:
        """Determine chunk position in section.

        Args:
            index: Chunk index (0-based).
            total: Total number of chunks.

        Returns:
            Position string: 'beginning', 'middle', or 'end'.
        """
        if total == 1:
            return "only"
        if index == 0:
            return "beginning"
        if index == total - 1:
            return "end"
        return "middle"

    def create_base_metadata(
        self,
        document: ParsedDocument,
        document_id: str,
    ) -> dict:
        """Create base metadata dict from document.

        Args:
            document: Parsed document.
            document_id: Document ID.

        Returns:
            Base metadata dictionary.
        """
        return {
            "document_id": document_id,
            "filename": document.metadata.filename,
            "file_type": document.metadata.file_type.value,
            "s3_uri": document.metadata.s3_uri,
            "module_name": document.metadata.module_name,
            "folder_path": document.metadata.folder_path,
            "week_number": document.metadata.week_number,
            "extraction_method": document.extraction_method,
        }

    def log_chunking_result(
        self,
        document: ParsedDocument,
        chunks: list[TextChunk],
    ) -> None:
        """Log chunking results.

        Args:
            document: Source document.
            chunks: Generated chunks.
        """
        total_tokens = sum(c.metadata.token_count for c in chunks)
        logger.info(
            "Document chunking complete",
            filename=document.metadata.filename,
            num_chunks=len(chunks),
            total_tokens=total_tokens,
            avg_tokens=total_tokens // len(chunks) if chunks else 0,
        )
