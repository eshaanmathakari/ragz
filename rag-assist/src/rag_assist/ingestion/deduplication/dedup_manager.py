"""Unified deduplication manager orchestrating hash and semantic dedup."""

from dataclasses import dataclass

import structlog

from rag_assist.config.settings import get_settings
from rag_assist.ingestion.deduplication.hash_dedup import (
    HashDeduplicator,
    HashDeduplicationStats,
)
from rag_assist.ingestion.deduplication.semantic_dedup import (
    SemanticDeduplicator,
    SemanticDeduplicationStats,
)
from rag_assist.ingestion.models import TextChunk

logger = structlog.get_logger(__name__)


@dataclass
class DeduplicationStats:
    """Combined deduplication statistics."""

    total_input_chunks: int = 0
    final_unique_chunks: int = 0

    # Hash dedup stats
    exact_duplicates: int = 0
    after_hash_dedup: int = 0

    # Semantic dedup stats
    near_duplicates: int = 0
    after_semantic_dedup: int = 0

    # Savings
    chunks_removed: int = 0
    removal_percentage: float = 0.0


class DeduplicationManager:
    """Two-stage deduplication manager.

    Stage 1: Exact hash deduplication (fast, catches identical content)
    Stage 2: Semantic deduplication (catches near-duplicates)
    """

    def __init__(
        self,
        enable_hash_dedup: bool | None = None,
        enable_semantic_dedup: bool | None = None,
        semantic_threshold: float | None = None,
    ):
        """Initialize deduplication manager.

        Args:
            enable_hash_dedup: Enable exact hash deduplication.
            enable_semantic_dedup: Enable semantic deduplication.
            semantic_threshold: Similarity threshold for semantic dedup.
        """
        settings = get_settings()

        self.enable_hash_dedup = (
            enable_hash_dedup if enable_hash_dedup is not None else settings.dedup.exact_hash
        )
        self.enable_semantic_dedup = (
            enable_semantic_dedup if enable_semantic_dedup is not None else settings.dedup.semantic
        )

        self.hash_deduplicator = HashDeduplicator()
        self.semantic_deduplicator = SemanticDeduplicator(threshold=semantic_threshold)

    def deduplicate(
        self,
        chunks: list[TextChunk],
        existing_hashes: set[str] | None = None,
    ) -> tuple[list[TextChunk], DeduplicationStats]:
        """Perform two-stage deduplication on chunks.

        Args:
            chunks: List of text chunks to deduplicate.
            existing_hashes: Set of content hashes already in the index.

        Returns:
            Tuple of (deduplicated chunks, stats).
        """
        stats = DeduplicationStats(total_input_chunks=len(chunks))

        if not chunks:
            return [], stats

        current_chunks = chunks

        # Stage 1: Hash deduplication
        if self.enable_hash_dedup:
            current_chunks, hash_stats = self.hash_deduplicator.deduplicate(
                current_chunks, existing_hashes
            )
            stats.exact_duplicates = hash_stats.duplicate_chunks
            stats.after_hash_dedup = len(current_chunks)
        else:
            stats.after_hash_dedup = len(current_chunks)

        # Stage 2: Semantic deduplication
        if self.enable_semantic_dedup and len(current_chunks) > 1:
            current_chunks, semantic_stats = self.semantic_deduplicator.deduplicate(
                current_chunks
            )
            stats.near_duplicates = semantic_stats.near_duplicate_chunks
            stats.after_semantic_dedup = len(current_chunks)
        else:
            stats.after_semantic_dedup = len(current_chunks)

        # Calculate final stats
        stats.final_unique_chunks = len(current_chunks)
        stats.chunks_removed = stats.total_input_chunks - stats.final_unique_chunks
        stats.removal_percentage = (
            (stats.chunks_removed / stats.total_input_chunks * 100)
            if stats.total_input_chunks > 0
            else 0.0
        )

        logger.info(
            "Deduplication complete",
            input_chunks=stats.total_input_chunks,
            output_chunks=stats.final_unique_chunks,
            exact_duplicates=stats.exact_duplicates,
            near_duplicates=stats.near_duplicates,
            removal_percentage=f"{stats.removal_percentage:.1f}%",
        )

        return current_chunks, stats

    def deduplicate_query_results(
        self,
        chunks: list[TextChunk],
        similarity_threshold: float = 0.85,
        max_chunks: int | None = None,
    ) -> list[TextChunk]:
        """Deduplicate retrieved chunks at query time.

        Uses a simpler approach for real-time query deduplication:
        - Greedy selection based on relevance score
        - Skip chunks too similar to already-selected ones

        Args:
            chunks: Retrieved chunks (assumed to be sorted by relevance).
            similarity_threshold: Similarity threshold for dedup.
            max_chunks: Maximum chunks to return.

        Returns:
            Deduplicated list of chunks.
        """
        if not chunks:
            return []

        selected = []
        selected_fingerprints: list[str] = []

        for chunk in chunks:
            if max_chunks and len(selected) >= max_chunks:
                break

            # Compute fingerprint if not present
            if not chunk.metadata.semantic_fingerprint:
                chunk.metadata.semantic_fingerprint = self.semantic_deduplicator.compute_fingerprint(
                    chunk.text
                )

            # Check similarity to already selected chunks
            is_similar = False
            chunk_fingerprint = chunk.metadata.semantic_fingerprint

            for existing_fp in selected_fingerprints:
                # Quick fingerprint comparison (not exact similarity)
                # For more accuracy, compute actual MinHash similarity
                if self._fingerprints_similar(chunk_fingerprint, existing_fp, similarity_threshold):
                    is_similar = True
                    break

            if not is_similar:
                selected.append(chunk)
                selected_fingerprints.append(chunk_fingerprint)

        logger.debug(
            f"Query dedup: {len(chunks)} -> {len(selected)} chunks"
        )

        return selected

    def _fingerprints_similar(
        self,
        fp1: str,
        fp2: str,
        threshold: float,
    ) -> bool:
        """Quick fingerprint similarity check.

        Args:
            fp1: First fingerprint.
            fp2: Second fingerprint.
            threshold: Similarity threshold.

        Returns:
            True if fingerprints are similar.
        """
        if not fp1 or not fp2:
            return False

        # Simple character overlap for fingerprints
        # For more accuracy, use actual MinHash Jaccard similarity
        min_len = min(len(fp1), len(fp2))
        matches = sum(1 for i in range(min_len) if fp1[i] == fp2[i])
        similarity = matches / min_len if min_len > 0 else 0

        return similarity >= threshold

    def get_seen_hashes(self) -> set[str]:
        """Get all content hashes seen during this session.

        Returns:
            Set of content hashes.
        """
        return self.hash_deduplicator.get_seen_hashes()

    def clear(self) -> None:
        """Clear all deduplication state."""
        self.hash_deduplicator.clear()
        self.semantic_deduplicator.clear()
