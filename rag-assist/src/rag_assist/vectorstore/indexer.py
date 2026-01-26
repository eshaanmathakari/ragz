"""Document indexer for ingesting chunks into OpenSearch."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog

from rag_assist.ingestion.models import TextChunk
from rag_assist.vectorstore.embedder import TitanEmbedder, get_embedder
from rag_assist.vectorstore.opensearch_client import OpenSearchClient, get_opensearch_client

logger = structlog.get_logger(__name__)


@dataclass
class IndexingStats:
    """Statistics for indexing operation."""

    total_chunks: int = 0
    indexed_successfully: int = 0
    indexing_failed: int = 0
    embedding_time_ms: float = 0
    indexing_time_ms: float = 0


class DocumentIndexer:
    """Indexes text chunks into OpenSearch with embeddings."""

    def __init__(
        self,
        opensearch_client: OpenSearchClient | None = None,
        embedder: TitanEmbedder | None = None,
        batch_size: int = 50,
    ):
        """Initialize document indexer.

        Args:
            opensearch_client: OpenSearch client instance.
            embedder: Titan embedder instance.
            batch_size: Number of documents per bulk index.
        """
        self.opensearch = opensearch_client or get_opensearch_client()
        self.embedder = embedder or get_embedder()
        self.batch_size = batch_size

    def index_chunks(
        self,
        chunks: list[TextChunk],
        generate_embeddings: bool = True,
    ) -> IndexingStats:
        """Index multiple chunks into OpenSearch.

        Args:
            chunks: List of text chunks to index.
            generate_embeddings: Generate embeddings if not present.

        Returns:
            Indexing statistics.
        """
        import time

        stats = IndexingStats(total_chunks=len(chunks))

        if not chunks:
            return stats

        # Generate embeddings if needed
        embedding_start = time.time()
        if generate_embeddings:
            chunks_needing_embeddings = [c for c in chunks if c.embedding is None]
            if chunks_needing_embeddings:
                logger.info(f"Generating embeddings for {len(chunks_needing_embeddings)} chunks")
                texts = [c.text for c in chunks_needing_embeddings]
                embeddings = self.embedder.embed_batch(texts)

                for chunk, embedding in zip(chunks_needing_embeddings, embeddings):
                    chunk.embedding = embedding

        stats.embedding_time_ms = (time.time() - embedding_start) * 1000

        # Prepare documents for indexing
        documents = []
        for chunk in chunks:
            doc = self._chunk_to_document(chunk)
            documents.append((chunk.metadata.chunk_id, doc))

        # Bulk index
        indexing_start = time.time()
        successful, failed = self.opensearch.bulk_index(
            documents=documents,
            chunk_size=self.batch_size,
        )

        stats.indexing_time_ms = (time.time() - indexing_start) * 1000
        stats.indexed_successfully = successful
        stats.indexing_failed = failed

        logger.info(
            "Indexing complete",
            total=stats.total_chunks,
            successful=stats.indexed_successfully,
            failed=stats.indexing_failed,
            embedding_time_ms=f"{stats.embedding_time_ms:.1f}",
            indexing_time_ms=f"{stats.indexing_time_ms:.1f}",
        )

        return stats

    def _chunk_to_document(self, chunk: TextChunk) -> dict[str, Any]:
        """Convert TextChunk to OpenSearch document.

        Args:
            chunk: Text chunk with metadata.

        Returns:
            Document dict for indexing.
        """
        meta = chunk.metadata

        doc = {
            "chunk_id": meta.chunk_id,
            "document_id": meta.document_id,
            "content": chunk.text,
            "content_embedding": chunk.embedding,
            # Source metadata
            "filename": meta.filename,
            "file_type": meta.file_type,
            "s3_uri": meta.s3_uri,
            "module_name": meta.module_name,
            "folder_path": meta.folder_path,
            "week_number": meta.week_number,
            # Location metadata
            "page_number": meta.page_number,
            "slide_number": meta.slide_number,
            "section_title": meta.section_title,
            "heading_hierarchy": meta.heading_hierarchy,
            "chunk_index": meta.chunk_index,
            "position_in_section": meta.position_in_section,
            "content_type": meta.content_type,
            # Semantic metadata
            "keywords": meta.keywords,
            "entities": meta.entities,
            "topic_tags": meta.topic_tags,
            "document_intent": meta.document_intent,
            # Deduplication metadata
            "content_hash": meta.content_hash,
            "semantic_fingerprint": meta.semantic_fingerprint,
            "canonical_chunk_id": meta.canonical_chunk_id,
            # Technical metadata
            "char_count": meta.char_count,
            "token_count": meta.token_count,
            "extraction_method": meta.extraction_method,
            "extraction_confidence": meta.extraction_confidence,
            # Timestamps
            "ingested_at": datetime.utcnow().isoformat(),
        }

        return doc

    def index_single(self, chunk: TextChunk) -> bool:
        """Index a single chunk.

        Args:
            chunk: Text chunk to index.

        Returns:
            True if indexing succeeded.
        """
        # Generate embedding if needed
        if chunk.embedding is None:
            chunk.embedding = self.embedder.embed(chunk.text)

        doc = self._chunk_to_document(chunk)
        return self.opensearch.index_document(chunk.metadata.chunk_id, doc)

    async def index_chunks_async(
        self,
        chunks: list[TextChunk],
    ) -> IndexingStats:
        """Index chunks asynchronously.

        Args:
            chunks: List of text chunks to index.

        Returns:
            Indexing statistics.
        """
        import asyncio

        stats = IndexingStats(total_chunks=len(chunks))

        if not chunks:
            return stats

        # Generate embeddings asynchronously
        chunks_needing_embeddings = [c for c in chunks if c.embedding is None]
        if chunks_needing_embeddings:
            logger.info(f"Generating embeddings async for {len(chunks_needing_embeddings)} chunks")
            texts = [c.text for c in chunks_needing_embeddings]
            embeddings = await self.embedder.embed_batch_async(texts)

            for chunk, embedding in zip(chunks_needing_embeddings, embeddings):
                chunk.embedding = embedding

        # Bulk index (synchronous for now)
        loop = asyncio.get_event_loop()
        documents = [(c.metadata.chunk_id, self._chunk_to_document(c)) for c in chunks]
        successful, failed = await loop.run_in_executor(
            None,
            lambda: self.opensearch.bulk_index(documents, self.batch_size),
        )

        stats.indexed_successfully = successful
        stats.indexing_failed = failed

        return stats

    def ensure_index_exists(self) -> bool:
        """Ensure the index exists, creating if necessary.

        Returns:
            True if index is ready.
        """
        if not self.opensearch.index_exists():
            logger.info("Creating index...")
            if not self.opensearch.create_index():
                return False

            logger.info("Creating search pipeline...")
            if not self.opensearch.create_search_pipeline():
                logger.warning("Failed to create search pipeline, hybrid search may not work")

        return True

    def get_index_stats(self) -> dict[str, Any]:
        """Get index statistics.

        Returns:
            Index statistics dict.
        """
        doc_count = self.opensearch.get_document_count()
        health = self.opensearch.health_check()

        return {
            "document_count": doc_count,
            "index_name": self.opensearch.index_name,
            "cluster_health": health,
        }
