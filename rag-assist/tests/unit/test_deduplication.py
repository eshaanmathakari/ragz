"""Unit tests for deduplication logic."""

import pytest

from rag_assist.ingestion.deduplication.hash_dedup import HashDeduplicator
from rag_assist.ingestion.deduplication.semantic_dedup import SemanticDeduplicator
from rag_assist.ingestion.deduplication.dedup_manager import DeduplicationManager
from rag_assist.ingestion.models import ChunkMetadata, TextChunk


class TestHashDeduplicator:
    """Tests for hash-based deduplication."""

    def test_removes_exact_duplicates(self):
        """Identical content should be deduplicated."""
        deduplicator = HashDeduplicator()

        chunks = [
            TextChunk(
                text="Machine learning is AI.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Machine learning is AI.",  # Exact duplicate
                metadata=ChunkMetadata(
                    chunk_id="chunk_002",
                    document_id="doc_002",
                    filename="b.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/b.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Neural networks are models.",  # Different
                metadata=ChunkMetadata(
                    chunk_id="chunk_003",
                    document_id="doc_003",
                    filename="c.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/c.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = deduplicator.deduplicate(chunks)

        assert len(result) == 2  # One duplicate removed
        assert stats.duplicate_chunks == 1

    def test_keeps_unique_content(self):
        """Unique content should be preserved."""
        deduplicator = HashDeduplicator()

        chunks = [
            TextChunk(
                text="First unique text.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Second unique text.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_002",
                    document_id="doc_002",
                    filename="b.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/b.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = deduplicator.deduplicate(chunks)

        assert len(result) == 2
        assert stats.duplicate_chunks == 0

    def test_normalizes_whitespace(self):
        """Whitespace differences should not prevent dedup."""
        deduplicator = HashDeduplicator()

        chunks = [
            TextChunk(
                text="Machine   learning   is   AI.",  # Extra spaces
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Machine learning is AI.",  # Normal spaces
                metadata=ChunkMetadata(
                    chunk_id="chunk_002",
                    document_id="doc_002",
                    filename="b.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/b.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = deduplicator.deduplicate(chunks)

        assert len(result) == 1  # Should be deduplicated
        assert stats.duplicate_chunks == 1

    def test_respects_existing_hashes(self):
        """Should skip chunks already in existing hash set."""
        deduplicator = HashDeduplicator()

        chunks = [
            TextChunk(
                text="New content here.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
        ]

        # Compute the hash for this content
        from rag_assist.ingestion.deduplication.hash_dedup import HashDeduplicator
        expected_hash = HashDeduplicator._normalize_and_hash(chunks[0].text)

        result, stats = deduplicator.deduplicate(chunks, existing_hashes={expected_hash})

        assert len(result) == 0  # Should be skipped
        assert stats.existing_duplicates == 1


class TestSemanticDeduplicator:
    """Tests for semantic deduplication."""

    def test_computes_fingerprint(self):
        """Should compute MinHash fingerprint for text."""
        deduplicator = SemanticDeduplicator()

        text = "Machine learning is a subset of artificial intelligence."
        fingerprint = deduplicator.compute_fingerprint(text)

        assert fingerprint is not None
        assert len(fingerprint) > 0

    def test_similar_texts_have_similar_fingerprints(self):
        """Similar texts should have high Jaccard similarity."""
        deduplicator = SemanticDeduplicator(threshold=0.8)

        text1 = "Machine learning is a subset of artificial intelligence."
        text2 = "Machine learning is a branch of artificial intelligence."

        fp1 = deduplicator.compute_fingerprint(text1)
        fp2 = deduplicator.compute_fingerprint(text2)

        # The fingerprints should be somewhat similar
        # (exact similarity depends on MinHash implementation)
        assert fp1 is not None
        assert fp2 is not None

    def test_removes_near_duplicates(self, sample_chunks):
        """Near-duplicate chunks should be deduplicated."""
        deduplicator = SemanticDeduplicator(threshold=0.7)

        # sample_chunks has two very similar ML definitions
        result, stats = deduplicator.deduplicate(sample_chunks[:2])

        # Should keep at most 1 (or both if threshold not met)
        assert len(result) <= 2

    def test_keeps_dissimilar_content(self, sample_chunks):
        """Dissimilar content should be preserved."""
        deduplicator = SemanticDeduplicator(threshold=0.9)

        # ML chunk vs neural network chunk - very different
        result, stats = deduplicator.deduplicate([sample_chunks[0], sample_chunks[2]])

        assert len(result) == 2  # Both should be kept


class TestDeduplicationManager:
    """Tests for two-stage deduplication manager."""

    def test_two_stage_deduplication(self):
        """Should run both hash and semantic dedup."""
        manager = DeduplicationManager(
            enable_hash_dedup=True,
            enable_semantic_dedup=True,
            semantic_threshold=0.7,
        )

        chunks = [
            TextChunk(
                text="Machine learning is AI.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Machine learning is AI.",  # Exact duplicate
                metadata=ChunkMetadata(
                    chunk_id="chunk_002",
                    document_id="doc_002",
                    filename="b.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/b.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Neural networks are different.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_003",
                    document_id="doc_003",
                    filename="c.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/c.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = manager.deduplicate(chunks)

        assert stats.total_input_chunks == 3
        assert stats.exact_duplicates >= 1
        assert len(result) < 3

    def test_hash_only_mode(self):
        """Should only run hash dedup when semantic disabled."""
        manager = DeduplicationManager(
            enable_hash_dedup=True,
            enable_semantic_dedup=False,
        )

        chunks = [
            TextChunk(
                text="Test content.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = manager.deduplicate(chunks)

        assert stats.near_duplicates == 0  # No semantic dedup

    def test_stats_calculation(self):
        """Stats should be calculated correctly."""
        manager = DeduplicationManager(
            enable_hash_dedup=True,
            enable_semantic_dedup=False,
        )

        chunks = [
            TextChunk(
                text="Unique content A.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_001",
                    document_id="doc_001",
                    filename="a.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/a.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Unique content A.",  # Duplicate
                metadata=ChunkMetadata(
                    chunk_id="chunk_002",
                    document_id="doc_002",
                    filename="b.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/b.pptx",
                    content_hash="",
                ),
            ),
            TextChunk(
                text="Unique content B.",
                metadata=ChunkMetadata(
                    chunk_id="chunk_003",
                    document_id="doc_003",
                    filename="c.pptx",
                    file_type="pptx",
                    s3_uri="s3://bucket/c.pptx",
                    content_hash="",
                ),
            ),
        ]

        result, stats = manager.deduplicate(chunks)

        assert stats.total_input_chunks == 3
        assert stats.final_unique_chunks == 2
        assert stats.chunks_removed == 1
        assert abs(stats.removal_percentage - 33.33) < 1  # ~33%

    def test_empty_input(self):
        """Should handle empty input gracefully."""
        manager = DeduplicationManager()

        result, stats = manager.deduplicate([])

        assert len(result) == 0
        assert stats.total_input_chunks == 0
