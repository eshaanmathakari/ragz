"""Unified content retrieval from OpenSearch.

This module handles:
- Text search using Cohere embeddings
- Linking text results with images by slide_number
- Generating presigned URLs for image access
- Hybrid search (text + image embeddings)
"""

from __future__ import annotations

import logging
from typing import Any

from embedders import CohereTextEmbedder
from models import RetrievalResult, SlideContent
from s3_store import S3ImageStore

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class PPTContentRetriever:
    """Retrieve PPT content with text + image context.

    Usage:
        retriever = PPTContentRetriever(
            opensearch_client=client,
            text_embedder=CohereTextEmbedder(),
            s3_store=S3ImageStore(bucket="my-bucket"),
        )

        # Search for content
        results = retriever.search("What is the architecture?")

        for r in results:
            print(f"Slide {r.slide_number}: {r.text_content[:100]}...")
            if r.image_presigned_url:
                # Display image
                print(f"Image: {r.image_presigned_url}")

        # Get all content for a specific slide
        slide = retriever.get_slide_content("doc123", slide_number=5)
    """

    def __init__(
        self,
        opensearch_client: Any,
        text_embedder: CohereTextEmbedder,
        s3_store: S3ImageStore,
        index_name: str = "ppt-content",
        presigned_url_expiration: int = 3600,
    ):
        """Initialize content retriever.

        Args:
            opensearch_client: OpenSearch client instance.
            text_embedder: Embedder for query text.
            s3_store: S3 store for image access.
            index_name: OpenSearch index name.
            presigned_url_expiration: Expiration time for presigned URLs (seconds).
        """
        self.client = opensearch_client
        self.text_embedder = text_embedder
        self.s3_store = s3_store
        self.index_name = index_name
        self.presigned_url_expiration = presigned_url_expiration

    def search(
        self,
        query: str,
        top_k: int = 5,
        include_images: bool = True,
        document_id: str | None = None,
    ) -> list[RetrievalResult]:
        """Search for content.

        1. Embed query with Cohere
        2. Search text embeddings in OpenSearch
        3. For each result, fetch linked images by slide_number
        4. Return text + image pairs

        Args:
            query: Search query text.
            top_k: Number of results to return.
            include_images: Whether to fetch linked images.
            document_id: Optional filter by document ID.

        Returns:
            List of RetrievalResult with text and linked images.
        """
        logger.info("Searching content", query=query[:50], top_k=top_k)

        # Embed query
        query_embedding = self.text_embedder.embed(query, input_type="search_query")

        if not query_embedding:
            logger.warning("Failed to embed query")
            return []

        # Build OpenSearch query
        must_clauses = [{"term": {"content_type": "text"}}]
        if document_id:
            must_clauses.append({"term": {"document_id": document_id}})

        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "should": [
                        {
                            "knn": {
                                "text_embedding": {
                                    "vector": query_embedding,
                                    "k": top_k,
                                }
                            }
                        }
                    ],
                }
            },
            "_source": [
                "content_id",
                "document_id",
                "filename",
                "slide_number",
                "text_content",
                "title",
                "source",
            ],
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        results: list[RetrievalResult] = []

        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            score = hit["_score"]

            result = RetrievalResult(
                document_id=source["document_id"],
                slide_number=source["slide_number"],
                filename=source.get("filename", ""),
                text_content=source.get("text_content", ""),
                title=source.get("title", ""),
                text_score=score,
                text_source=source.get("source", "ppt"),
            )

            # Fetch linked image if requested
            if include_images:
                image_info = self._get_linked_image(
                    source["document_id"], source["slide_number"]
                )
                if image_info:
                    result.image_s3_uri = image_info.get("image_s3_uri")
                    result.image_score = image_info.get("score")

                    # Generate presigned URL
                    if result.image_s3_uri:
                        try:
                            result.image_presigned_url = self.s3_store.get_presigned_url(
                                result.image_s3_uri,
                                expiration=self.presigned_url_expiration,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to generate presigned URL: {e}")

            results.append(result)

        logger.info("Search complete", results=len(results))
        return results

    def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[RetrievalResult]:
        """Search using image similarity.

        Args:
            image_bytes: Query image bytes.
            top_k: Number of results to return.
            document_id: Optional filter by document ID.

        Returns:
            List of RetrievalResult.
        """
        from embedders import TitanMultimodalEmbedder

        # Need image embedder for this
        image_embedder = TitanMultimodalEmbedder()
        query_embedding = image_embedder.embed_image(image_bytes)

        if not query_embedding:
            logger.warning("Failed to embed query image")
            return []

        # Search image embeddings
        must_clauses = [{"term": {"content_type": "image"}}]
        if document_id:
            must_clauses.append({"term": {"document_id": document_id}})

        search_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "should": [
                        {
                            "knn": {
                                "image_embedding": {
                                    "vector": query_embedding,
                                    "k": top_k,
                                }
                            }
                        }
                    ],
                }
            },
            "_source": [
                "content_id",
                "document_id",
                "filename",
                "slide_number",
                "image_s3_uri",
            ],
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        results: list[RetrievalResult] = []

        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            score = hit["_score"]

            result = RetrievalResult(
                document_id=source["document_id"],
                slide_number=source["slide_number"],
                filename=source.get("filename", ""),
                image_s3_uri=source.get("image_s3_uri"),
                image_score=score,
            )

            # Generate presigned URL
            if result.image_s3_uri:
                try:
                    result.image_presigned_url = self.s3_store.get_presigned_url(
                        result.image_s3_uri,
                        expiration=self.presigned_url_expiration,
                    )
                except Exception as e:
                    logger.warning(f"Failed to generate presigned URL: {e}")

            # Fetch linked text
            text_info = self._get_linked_text(
                source["document_id"], source["slide_number"]
            )
            if text_info:
                result.text_content = text_info.get("text_content", "")
                result.title = text_info.get("title", "")
                result.text_source = text_info.get("source", "ppt")

            results.append(result)

        return results

    def get_slide_content(
        self,
        document_id: str,
        slide_number: int,
    ) -> SlideContent | None:
        """Get all content for a specific slide.

        Args:
            document_id: Document identifier.
            slide_number: Slide number (1-indexed).

        Returns:
            SlideContent with all text and image data, or None if not found.
        """
        # Search for all content for this slide
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"slide_number": slide_number}},
                    ]
                }
            },
            "_source": True,
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        if response["hits"]["total"]["value"] == 0:
            return None

        slide = SlideContent(
            document_id=document_id,
            slide_number=slide_number,
        )

        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            content_type = source.get("content_type")

            if content_type == "text":
                if source.get("source") == "ppt":
                    # Create SlideTextContent from source
                    from models import SlideTextContent
                    slide.ppt_text = SlideTextContent(
                        document_id=source["document_id"],
                        filename=source.get("filename", ""),
                        slide_number=source["slide_number"],
                        title=source.get("title", ""),
                        body_text=source.get("text_content", ""),
                    )
                    slide.filename = source.get("filename", "")
                elif source.get("source") == "pdf":
                    slide.pdf_text = source.get("text_content", "")

            elif content_type == "image":
                slide.pdf_image_s3_uri = source.get("image_s3_uri")
                if slide.pdf_image_s3_uri:
                    try:
                        slide.pdf_image_presigned_url = self.s3_store.get_presigned_url(
                            slide.pdf_image_s3_uri,
                            expiration=self.presigned_url_expiration,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to generate presigned URL: {e}")

        return slide

    def list_documents(self) -> list[dict[str, Any]]:
        """List all indexed documents.

        Returns:
            List of document info dicts.
        """
        search_body = {
            "size": 0,
            "aggs": {
                "documents": {
                    "terms": {
                        "field": "document_id",
                        "size": 1000,
                    },
                    "aggs": {
                        "filename": {
                            "terms": {"field": "filename", "size": 1}
                        },
                        "text_count": {
                            "filter": {"term": {"content_type": "text"}}
                        },
                        "image_count": {
                            "filter": {"term": {"content_type": "image"}}
                        },
                    },
                }
            },
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        documents = []
        for bucket in response["aggregations"]["documents"]["buckets"]:
            doc_id = bucket["key"]
            filename_buckets = bucket["filename"]["buckets"]
            filename = filename_buckets[0]["key"] if filename_buckets else ""

            documents.append({
                "document_id": doc_id,
                "filename": filename,
                "text_count": bucket["text_count"]["doc_count"],
                "image_count": bucket["image_count"]["doc_count"],
                "total_count": bucket["doc_count"],
            })

        return documents

    def _get_linked_image(
        self, document_id: str, slide_number: int
    ) -> dict[str, Any] | None:
        """Get image for a text result by slide_number."""
        search_body = {
            "size": 1,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"slide_number": slide_number}},
                        {"term": {"content_type": "image"}},
                    ]
                }
            },
            "_source": ["image_s3_uri"],
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        if response["hits"]["hits"]:
            hit = response["hits"]["hits"][0]
            return {
                "image_s3_uri": hit["_source"].get("image_s3_uri"),
                "score": hit["_score"],
            }

        return None

    def _get_linked_text(
        self, document_id: str, slide_number: int
    ) -> dict[str, Any] | None:
        """Get text for an image result by slide_number."""
        search_body = {
            "size": 1,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"slide_number": slide_number}},
                        {"term": {"content_type": "text"}},
                    ]
                }
            },
            "_source": ["text_content", "title", "source"],
        }

        response = self.client.search(
            index=self.index_name,
            body=search_body,
        )

        if response["hits"]["hits"]:
            return response["hits"]["hits"][0]["_source"]

        return None
