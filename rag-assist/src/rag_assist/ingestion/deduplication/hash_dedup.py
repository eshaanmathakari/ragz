"""Exact hash-based deduplication."""

import hashlib
import re
from dataclasses import dataclass, field

import structlog

from rag_assist.ingestion.models import TextChunk

logger = structlog.get_logger(__name__)


@dataclass
class HashDeduplicationStats:
    """Statistics for hash deduplication."""

    total_chunks: int = 0
    unique_chunks: int = 0
    duplicate_chunks: int = 0
    duplicate_hashes: dict[str, list[str]] = field(default_factory=dict)


class HashDeduplicator:
    """Exact hash-based deduplication using SHA-256.

    Detects identical chunks by computing a normalized hash of the content.
    """

    def __init__(
        self,
        normalize_whitespace: bool = True,
        normalize_case: bool = True,
        remove_punctuation: bool = True,
    ):
        """Initialize hash deduplicator.

        Args:
            normalize_whitespace: Collapse multiple whitespace to single space.
            normalize_case: Convert to lowercase before hashing.
            remove_punctuation: Remove punctuation before hashing.
        """
        self.normalize_whitespace = normalize_whitespace
        self.normalize_case = normalize_case
        self.remove_punctuation = remove_punctuation

        # Track seen hashes
        self._seen_hashes: dict[str, str] = {}  # hash -> first chunk_id

    def normalize_text(self, text: str) -> str:
        """Normalize text for consistent hashing.

        Args:
            text: Raw text.

        Returns:
            Normalized text.
        """
        if not text:
            return ""

        normalized = text

        if self.normalize_case:
            normalized = normalized.lower()

        if self.normalize_whitespace:
            normalized = re.sub(r"\s+", " ", normalized)

        if self.remove_punctuation:
            normalized = re.sub(r"[^\w\s]", "", normalized)

        return normalized.strip()

    def compute_hash(self, text: str) -> str:
        """Compute SHA-256 hash of normalized text.

        Args:
            text: Text to hash.

        Returns:
            SHA-256 hash string.
        """
        normalized = self.normalize_text(text)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def is_duplicate(self, chunk: TextChunk) -> bool:
        """Check if chunk is a duplicate.

        Args:
            chunk: Text chunk to check.

        Returns:
            True if this is a duplicate of a previously seen chunk.
        """
        content_hash = self.compute_hash(chunk.text)
        return content_hash in self._seen_hashes

    def register(self, chunk: TextChunk) -> str:
        """Register a chunk and return its hash.

        Args:
            chunk: Text chunk to register.

        Returns:
            Content hash.
        """
        content_hash = self.compute_hash(chunk.text)

        if content_hash not in self._seen_hashes:
            self._seen_hashes[content_hash] = chunk.metadata.chunk_id

        return content_hash

    def deduplicate(
        self,
        chunks: list[TextChunk],
        existing_hashes: set[str] | None = None,
    ) -> tuple[list[TextChunk], HashDeduplicationStats]:
        """Deduplicate a list of chunks.

        Args:
            chunks: List of text chunks.
            existing_hashes: Set of already-indexed content hashes.

        Returns:
            Tuple of (unique chunks, deduplication stats).
        """
        existing_hashes = existing_hashes or set()
        stats = HashDeduplicationStats(total_chunks=len(chunks))

        unique_chunks = []
        batch_hashes: dict[str, str] = {}  # hash -> chunk_id for this batch

        for chunk in chunks:
            content_hash = self.compute_hash(chunk.text)

            # Update chunk metadata with hash
            chunk.metadata.content_hash = content_hash

            # Check against existing index
            if content_hash in existing_hashes:
                stats.duplicate_chunks += 1
                if content_hash not in stats.duplicate_hashes:
                    stats.duplicate_hashes[content_hash] = []
                stats.duplicate_hashes[content_hash].append(chunk.metadata.chunk_id)
                continue

            # Check against current batch
            if content_hash in batch_hashes:
                stats.duplicate_chunks += 1
                # Set canonical reference
                chunk.metadata.canonical_chunk_id = batch_hashes[content_hash]
                if content_hash not in stats.duplicate_hashes:
                    stats.duplicate_hashes[content_hash] = []
                stats.duplicate_hashes[content_hash].append(chunk.metadata.chunk_id)
                continue

            # Check against previously seen in this session
            if content_hash in self._seen_hashes:
                stats.duplicate_chunks += 1
                chunk.metadata.canonical_chunk_id = self._seen_hashes[content_hash]
                continue

            # New unique chunk
            batch_hashes[content_hash] = chunk.metadata.chunk_id
            self._seen_hashes[content_hash] = chunk.metadata.chunk_id
            unique_chunks.append(chunk)

        stats.unique_chunks = len(unique_chunks)

        logger.info(
            "Hash deduplication complete",
            total=stats.total_chunks,
            unique=stats.unique_chunks,
            duplicates=stats.duplicate_chunks,
        )

        return unique_chunks, stats

    def clear(self) -> None:
        """Clear seen hashes."""
        self._seen_hashes.clear()

    def get_seen_hashes(self) -> set[str]:
        """Get all seen content hashes.

        Returns:
            Set of content hashes.
        """
        return set(self._seen_hashes.keys())
