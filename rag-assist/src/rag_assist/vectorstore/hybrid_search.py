"""Hybrid search combining vector similarity and keyword search."""

from dataclasses import dataclass, field
from typing import Any

import structlog

from rag_assist.config.settings import get_settings
from rag_assist.ingestion.models import ChunkMetadata, TextChunk
from rag_assist.vectorstore.embedder import TitanEmbedder, get_embedder
from rag_assist.vectorstore.opensearch_client import OpenSearchClient, get_opensearch_client

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    """A single search result with score and metadata."""

    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_text_chunk(self) -> TextChunk:
        """Convert to TextChunk for downstream processing."""
        chunk_metadata = ChunkMetadata(
            chunk_id=self.chunk_id,
            document_id=self.metadata.get("document_id", ""),
            filename=self.metadata.get("filename", ""),
            file_type=self.metadata.get("file_type", ""),
            s3_uri=self.metadata.get("s3_uri", ""),
            module_name=self.metadata.get("module_name", ""),
            folder_path=self.metadata.get("folder_path", ""),
            week_number=self.metadata.get("week_number"),
            page_number=self.metadata.get("page_number"),
            slide_number=self.metadata.get("slide_number"),
            section_title=self.metadata.get("section_title"),
            heading_hierarchy=self.metadata.get("heading_hierarchy", []),
            keywords=self.metadata.get("keywords", []),
            topic_tags=self.metadata.get("topic_tags", []),
            content_hash=self.metadata.get("content_hash", ""),
            semantic_fingerprint=self.metadata.get("semantic_fingerprint", ""),
            token_count=self.metadata.get("token_count", 0),
        )
        return TextChunk(text=self.text, metadata=chunk_metadata)


@dataclass
class SearchResponse:
    """Complete search response."""

    results: list[SearchResult]
    total_hits: int
    query_time_ms: float
    query_text: str


class HybridSearcher:
    """Hybrid search combining vector and keyword search.

    Uses OpenSearch's hybrid query with configurable weights
    for vector similarity and BM25 keyword matching.
    """

    def __init__(
        self,
        opensearch_client: OpenSearchClient | None = None,
        embedder: TitanEmbedder | None = None,
        vector_weight: float | None = None,
        keyword_weight: float | None = None,
    ):
        """Initialize hybrid searcher.

        Args:
            opensearch_client: OpenSearch client instance.
            embedder: Titan embedder instance.
            vector_weight: Weight for vector search (0-1).
            keyword_weight: Weight for keyword search (0-1).
        """
        settings = get_settings()

        self.opensearch = opensearch_client or get_opensearch_client()
        self.embedder = embedder or get_embedder()
        self.vector_weight = vector_weight or settings.rag.vector_weight
        self.keyword_weight = keyword_weight or settings.rag.keyword_weight

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> SearchResponse:
        """Execute hybrid search.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            filters: Metadata filters (week_number, file_type, etc.).
            min_score: Minimum score threshold.

        Returns:
            SearchResponse with results.
        """
        import time

        start_time = time.time()

        # Generate query embedding
        query_embedding = self.embedder.embed(query)

        # Build hybrid query
        search_query = self._build_hybrid_query(
            query_text=query,
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )

        # Execute search
        try:
            response = self.opensearch.search(
                query=search_query,
                size=top_k,
                use_pipeline=True,
            )
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return SearchResponse(
                results=[],
                total_hits=0,
                query_time_ms=0,
                query_text=query,
            )

        # Parse results
        results = self._parse_results(response, min_score)

        query_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Hybrid search complete",
            query_length=len(query),
            results=len(results),
            query_time_ms=f"{query_time_ms:.1f}",
        )

        return SearchResponse(
            results=results,
            total_hits=response.get("hits", {}).get("total", {}).get("value", 0),
            query_time_ms=query_time_ms,
            query_text=query,
        )

    def _build_hybrid_query(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build OpenSearch hybrid query.

        Args:
            query_text: Text query for keyword search.
            query_embedding: Query embedding for vector search.
            top_k: Number of results.
            filters: Metadata filters.

        Returns:
            OpenSearch query body.
        """
        # Vector search query
        vector_query = {
            "knn": {
                "content_embedding": {
                    "vector": query_embedding,
                    "k": top_k,
                }
            }
        }

        # Keyword search query (BM25)
        keyword_query = {
            "multi_match": {
                "query": query_text,
                "fields": [
                    "content^2",
                    "section_title^1.5",
                    "keywords^1.5",
                    "topic_tags",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        }

        # Hybrid query combining both
        hybrid_query = {
            "hybrid": {
                "queries": [vector_query, keyword_query]
            }
        }

        # Build filter clause if filters provided
        filter_clause = self._build_filters(filters) if filters else None

        # Construct final query
        if filter_clause:
            query_body = {
                "query": {
                    "bool": {
                        "must": hybrid_query,
                        "filter": filter_clause,
                    }
                }
            }
        else:
            query_body = {"query": hybrid_query}

        # Add source fields to return
        query_body["_source"] = {
            "includes": [
                "content",
                "document_id",
                "filename",
                "file_type",
                "s3_uri",
                "module_name",
                "folder_path",
                "week_number",
                "page_number",
                "slide_number",
                "section_title",
                "heading_hierarchy",
                "keywords",
                "topic_tags",
                "content_hash",
                "semantic_fingerprint",
                "token_count",
            ]
        }

        return query_body

    def _build_filters(self, filters: dict[str, Any]) -> list[dict]:
        """Build filter clauses from filter dict.

        Args:
            filters: Filter specifications.

        Returns:
            List of filter clauses.
        """
        clauses = []

        if "week_number" in filters:
            week = filters["week_number"]
            if isinstance(week, list):
                clauses.append({"terms": {"week_number": week}})
            else:
                clauses.append({"term": {"week_number": week}})

        if "file_type" in filters:
            file_types = filters["file_type"]
            if isinstance(file_types, list):
                clauses.append({"terms": {"file_type": file_types}})
            else:
                clauses.append({"term": {"file_type": file_types}})

        if "module_name" in filters:
            clauses.append({"match": {"module_name": filters["module_name"]}})

        if "topics" in filters:
            topics = filters["topics"]
            if isinstance(topics, list):
                clauses.append({"terms": {"topic_tags": topics}})
            else:
                clauses.append({"term": {"topic_tags": topics}})

        if "keywords" in filters:
            keywords = filters["keywords"]
            if isinstance(keywords, list):
                clauses.append({"terms": {"keywords": keywords}})
            else:
                clauses.append({"term": {"keywords": keywords}})

        return clauses

    def _parse_results(
        self,
        response: dict[str, Any],
        min_score: float,
    ) -> list[SearchResult]:
        """Parse OpenSearch response into SearchResults.

        Args:
            response: OpenSearch response dict.
            min_score: Minimum score threshold.

        Returns:
            List of SearchResult objects.
        """
        results = []

        hits = response.get("hits", {}).get("hits", [])

        for hit in hits:
            score = hit.get("_score", 0)

            if score < min_score:
                continue

            source = hit.get("_source", {})

            result = SearchResult(
                chunk_id=hit.get("_id", ""),
                text=source.get("content", ""),
                score=score,
                metadata={
                    "document_id": source.get("document_id"),
                    "filename": source.get("filename"),
                    "file_type": source.get("file_type"),
                    "s3_uri": source.get("s3_uri"),
                    "module_name": source.get("module_name"),
                    "folder_path": source.get("folder_path"),
                    "week_number": source.get("week_number"),
                    "page_number": source.get("page_number"),
                    "slide_number": source.get("slide_number"),
                    "section_title": source.get("section_title"),
                    "heading_hierarchy": source.get("heading_hierarchy", []),
                    "keywords": source.get("keywords", []),
                    "topic_tags": source.get("topic_tags", []),
                    "content_hash": source.get("content_hash"),
                    "semantic_fingerprint": source.get("semantic_fingerprint"),
                    "token_count": source.get("token_count", 0),
                },
            )
            results.append(result)

        return results

    def search_vector_only(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> SearchResponse:
        """Execute vector-only search (for debugging/comparison).

        Args:
            query: Search query text.
            top_k: Number of results.
            filters: Metadata filters.

        Returns:
            SearchResponse with results.
        """
        import time

        start_time = time.time()

        query_embedding = self.embedder.embed(query)

        search_query = {
            "query": {
                "knn": {
                    "content_embedding": {
                        "vector": query_embedding,
                        "k": top_k,
                    }
                }
            }
        }

        if filters:
            filter_clause = self._build_filters(filters)
            search_query["query"] = {
                "bool": {
                    "must": search_query["query"],
                    "filter": filter_clause,
                }
            }

        response = self.opensearch.search(
            query=search_query,
            size=top_k,
            use_pipeline=False,
        )

        results = self._parse_results(response, 0.0)
        query_time_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=results,
            total_hits=response.get("hits", {}).get("total", {}).get("value", 0),
            query_time_ms=query_time_ms,
            query_text=query,
        )

    def search_keyword_only(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> SearchResponse:
        """Execute keyword-only search (for debugging/comparison).

        Args:
            query: Search query text.
            top_k: Number of results.
            filters: Metadata filters.

        Returns:
            SearchResponse with results.
        """
        import time

        start_time = time.time()

        search_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["content^2", "section_title^1.5", "keywords"],
                    "type": "best_fields",
                }
            }
        }

        if filters:
            filter_clause = self._build_filters(filters)
            search_query["query"] = {
                "bool": {
                    "must": search_query["query"],
                    "filter": filter_clause,
                }
            }

        response = self.opensearch.search(
            query=search_query,
            size=top_k,
            use_pipeline=False,
        )

        results = self._parse_results(response, 0.0)
        query_time_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            results=results,
            total_hits=response.get("hits", {}).get("total", {}).get("value", 0),
            query_time_ms=query_time_ms,
            query_text=query,
        )
