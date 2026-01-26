"""Semantic deduplication using MinHash LSH."""

import re
from dataclasses import dataclass, field

import structlog
from datasketch import MinHash, MinHashLSH

from rag_assist.config.settings import get_settings
from rag_assist.ingestion.models import TextChunk

logger = structlog.get_logger(__name__)


@dataclass
class SemanticDeduplicationStats:
    """Statistics for semantic deduplication."""

    total_chunks: int = 0
    unique_chunks: int = 0
    near_duplicate_chunks: int = 0
    clusters: dict[str, list[str]] = field(default_factory=dict)  # canonical_id -> duplicate_ids


class SemanticDeduplicator:
    """Semantic deduplication using MinHash Locality Sensitive Hashing.

    Detects near-duplicate chunks based on text similarity.
    Uses MinHash for efficient approximate similarity detection.
    """

    def __init__(
        self,
        threshold: float | None = None,
        num_perm: int | None = None,
        ngram_size: int = 3,
    ):
        """Initialize semantic deduplicator.

        Args:
            threshold: Jaccard similarity threshold for near-duplicates.
            num_perm: Number of permutations for MinHash.
            ngram_size: Size of character n-grams for shingling.
        """
        settings = get_settings()

        self.threshold = threshold or settings.dedup.semantic_threshold
        self.num_perm = num_perm or settings.dedup.minhash_num_perm
        self.ngram_size = ngram_size

        # Initialize LSH index
        self._lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self._chunk_minhashes: dict[str, MinHash] = {}  # chunk_id -> minhash

    def _create_shingles(self, text: str) -> set[str]:
        """Create character n-gram shingles from text.

        Args:
            text: Text to shingle.

        Returns:
            Set of n-gram shingles.
        """
        # Normalize text
        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        if len(text) < self.ngram_size:
            return {text}

        # Create character n-grams
        shingles = set()
        for i in range(len(text) - self.ngram_size + 1):
            shingle = text[i : i + self.ngram_size]
            shingles.add(shingle)

        return shingles

    def compute_minhash(self, text: str) -> MinHash:
        """Compute MinHash signature for text.

        Args:
            text: Text to compute MinHash for.

        Returns:
            MinHash object.
        """
        minhash = MinHash(num_perm=self.num_perm)
        shingles = self._create_shingles(text)

        for shingle in shingles:
            minhash.update(shingle.encode("utf-8"))

        return minhash

    def compute_fingerprint(self, text: str) -> str:
        """Compute a fingerprint string from MinHash.

        Args:
            text: Text to fingerprint.

        Returns:
            Hex string fingerprint.
        """
        minhash = self.compute_minhash(text)
        # Use first 16 hash values as fingerprint
        hash_values = minhash.hashvalues[:16]
        return "".join(f"{h:08x}" for h in hash_values)

    def find_similar(self, chunk: TextChunk) -> list[str]:
        """Find similar chunks in the index.

        Args:
            chunk: Text chunk to search for.

        Returns:
            List of similar chunk IDs.
        """
        minhash = self.compute_minhash(chunk.text)
        return self._lsh.query(minhash)

    def register(self, chunk: TextChunk) -> None:
        """Register a chunk in the LSH index.

        Args:
            chunk: Text chunk to register.
        """
        minhash = self.compute_minhash(chunk.text)
        chunk_id = chunk.metadata.chunk_id

        # Store minhash for later similarity computation
        self._chunk_minhashes[chunk_id] = minhash

        # Insert into LSH index
        try:
            self._lsh.insert(chunk_id, minhash)
        except ValueError:
            # Key already exists
            pass

    def compute_similarity(self, chunk1: TextChunk, chunk2: TextChunk) -> float:
        """Compute Jaccard similarity between two chunks.

        Args:
            chunk1: First chunk.
            chunk2: Second chunk.

        Returns:
            Jaccard similarity (0-1).
        """
        mh1 = self.compute_minhash(chunk1.text)
        mh2 = self.compute_minhash(chunk2.text)
        return mh1.jaccard(mh2)

    def deduplicate(
        self,
        chunks: list[TextChunk],
    ) -> tuple[list[TextChunk], SemanticDeduplicationStats]:
        """Deduplicate chunks based on semantic similarity.

        Args:
            chunks: List of text chunks (should be hash-deduplicated first).

        Returns:
            Tuple of (unique chunks, deduplication stats).
        """
        stats = SemanticDeduplicationStats(total_chunks=len(chunks))

        unique_chunks = []
        processed_ids: set[str] = set()

        for chunk in chunks:
            chunk_id = chunk.metadata.chunk_id

            if chunk_id in processed_ids:
                continue

            # Compute and store fingerprint
            fingerprint = self.compute_fingerprint(chunk.text)
            chunk.metadata.semantic_fingerprint = fingerprint

            # Query LSH for similar chunks
            minhash = self.compute_minhash(chunk.text)
            similar_ids = self._lsh.query(minhash)

            # Filter to actual similar chunks (exclude self if already indexed)
            similar_ids = [sid for sid in similar_ids if sid != chunk_id and sid not in processed_ids]

            if similar_ids:
                # This chunk is similar to an existing one
                stats.near_duplicate_chunks += 1

                # Use the first similar as canonical
                canonical_id = similar_ids[0]
                chunk.metadata.canonical_chunk_id = canonical_id

                if canonical_id not in stats.clusters:
                    stats.clusters[canonical_id] = []
                stats.clusters[canonical_id].append(chunk_id)

                processed_ids.add(chunk_id)
                continue

            # Register new unique chunk
            try:
                self._lsh.insert(chunk_id, minhash)
                self._chunk_minhashes[chunk_id] = minhash
            except ValueError:
                pass

            unique_chunks.append(chunk)
            processed_ids.add(chunk_id)

        stats.unique_chunks = len(unique_chunks)

        logger.info(
            "Semantic deduplication complete",
            total=stats.total_chunks,
            unique=stats.unique_chunks,
            near_duplicates=stats.near_duplicate_chunks,
            clusters=len(stats.clusters),
        )

        return unique_chunks, stats

    def clear(self) -> None:
        """Clear the LSH index."""
        self._lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        self._chunk_minhashes.clear()
