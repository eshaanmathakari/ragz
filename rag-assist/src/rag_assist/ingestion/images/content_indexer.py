"""Content indexer for PPT text and images to OpenSearch.

This module handles:
1. Step 1: Index text from PPTX (primary text source)
2. Step 2: Index images from PDF + unique PDF text
3. Link content by document_id + slide_number

Text and images are stored as separate documents in OpenSearch,
linked by document_id and slide_number for unified retrieval.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from embedders import CohereTextEmbedder, TitanMultimodalEmbedder
from models import (
    IndexedImageDocument,
    IndexedTextDocument,
    IndexingResult,
    PageTextContent,
    PDFPageContent,
    PPTExtractionResult,
    SlideTextContent,
)
from pdf_content_extractor import PDFContentExtractor
from ppt_text_extractor import PPTXTextExtractor
from s3_store import S3ImageStore
from text_deduplicator import TextDeduplicator

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


# OpenSearch index mapping
OPENSEARCH_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "content_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "filename": {"type": "keyword"},
            "slide_number": {"type": "integer"},
            "content_type": {"type": "keyword"},  # "text" or "image"
            "source": {"type": "keyword"},  # "ppt" or "pdf"
            # Text fields
            "text_content": {"type": "text"},
            "title": {"type": "text"},
            "text_embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "faiss",
                },
            },
            # Image fields
            "image_s3_uri": {"type": "keyword"},
            "width_px": {"type": "integer"},
            "height_px": {"type": "integer"},
            "image_embedding": {
                "type": "knn_vector",
                "dimension": 1024,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "faiss",
                },
            },
            # Metadata
            "created_at": {"type": "date"},
        }
    }
}


class PPTContentIndexer:
    """Index PPT content (text + images) to OpenSearch.

    Usage:
        indexer = PPTContentIndexer(
            opensearch_client=client,
            text_embedder=CohereTextEmbedder(),
            image_embedder=TitanMultimodalEmbedder(),
            s3_store=S3ImageStore(bucket="my-bucket"),
        )

        # Step 1: Index PPT text
        result1 = indexer.index_ppt_text("presentation.pptx")

        # Step 2: Index PDF images + unique text
        result2 = indexer.index_pdf_content(
            "presentation.pdf",
            document_id=result1.document_id
        )
    """

    def __init__(
        self,
        opensearch_client: Any,
        text_embedder: CohereTextEmbedder,
        image_embedder: TitanMultimodalEmbedder,
        s3_store: S3ImageStore,
        index_name: str = "ppt-content",
        similarity_threshold: float = 0.85,
    ):
        """Initialize content indexer.

        Args:
            opensearch_client: OpenSearch client instance.
            text_embedder: Embedder for text content.
            image_embedder: Embedder for images.
            s3_store: S3 store for images.
            index_name: OpenSearch index name.
            similarity_threshold: Threshold for text deduplication.
        """
        self.client = opensearch_client
        self.text_embedder = text_embedder
        self.image_embedder = image_embedder
        self.s3_store = s3_store
        self.index_name = index_name
        self.similarity_threshold = similarity_threshold

        self._ppt_extractor = PPTXTextExtractor()
        self._pdf_extractor = PDFContentExtractor()
        self._deduplicator = TextDeduplicator(similarity_threshold)

    def ensure_index_exists(self) -> None:
        """Create OpenSearch index if it doesn't exist."""
        try:
            if not self.client.indices.exists(index=self.index_name):
                self.client.indices.create(
                    index=self.index_name,
                    body=OPENSEARCH_INDEX_MAPPING,
                )
                logger.info("Created OpenSearch index", index=self.index_name)
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise

    def index_ppt_text(
        self,
        pptx_path: str,
        document_id: str | None = None,
    ) -> IndexingResult:
        """Step 1: Index text from PPTX.

        Args:
            pptx_path: Path to PPTX file.
            document_id: Optional document ID. Auto-generated if not provided.

        Returns:
            IndexingResult with indexing details.
        """
        logger.info("Step 1: Indexing PPT text", path=pptx_path)
        ppt_result = self._ppt_extractor.extract(pptx_path)
        if document_id:
            ppt_result.document_id = document_id
            for slide in ppt_result.slides:
                slide.document_id = document_id
        return self.index_ppt_slides(ppt_result, document_id)

    def index_ppt_slides(
        self,
        ppt_result: PPTExtractionResult,
        document_id: str | None = None,
    ) -> IndexingResult:
        """Index text from an already-extracted PPT result (avoids re-extraction).

        Args:
            ppt_result: Result from PPTXTextExtractor.extract().
            document_id: Optional override for document_id.

        Returns:
            IndexingResult with indexing details.
        """
        if document_id:
            ppt_result.document_id = document_id
            for slide in ppt_result.slides:
                slide.document_id = document_id

        errors: list[str] = list(ppt_result.errors)
        text_indexed = 0

        for slide in ppt_result.slides:
            try:
                # Get text to embed
                text = slide.full_text
                if not text.strip():
                    continue

                # Generate embedding
                embedding = self.text_embedder.embed(text)

                # Create document
                doc = IndexedTextDocument(
                    content_id=slide.content_id,
                    document_id=slide.document_id,
                    filename=slide.filename,
                    slide_number=slide.slide_number,
                    content_type="text",
                    source="ppt",
                    text_content=text,
                    title=slide.title,
                    text_embedding=embedding,
                )

                # Index to OpenSearch
                self.client.index(
                    index=self.index_name,
                    id=doc.content_id,
                    body=doc.to_opensearch_doc(),
                )
                text_indexed += 1

            except Exception as e:
                error_msg = f"Failed to index slide {slide.slide_number}: {e}"
                errors.append(error_msg)
                logger.warning(error_msg)

        logger.info(
            "PPT text indexing complete",
            document_id=ppt_result.document_id,
            slides_indexed=text_indexed,
            errors=len(errors),
        )

        return IndexingResult(
            document_id=ppt_result.document_id,
            filename=ppt_result.filename,
            text_documents_indexed=text_indexed,
            errors=errors,
        )

    def index_pdf_content(
        self,
        pdf_path: str,
        document_id: str,
        ppt_slides: list[SlideTextContent] | None = None,
    ) -> IndexingResult:
        """Step 2: Index images (and unique text) from PDF.

        Args:
            pdf_path: Path to PDF file.
            document_id: Document ID (must match PPT document_id).
            ppt_slides: Optional PPT slides for deduplication.
                       If provided, duplicate text won't be indexed.

        Returns:
            IndexingResult with indexing details.
        """
        logger.info("Step 2: Indexing PDF content", path=pdf_path, document_id=document_id)

        # Extract content from PDF
        pdf_result = self._pdf_extractor.extract(pdf_path, document_id=document_id)

        errors: list[str] = list(pdf_result.errors)
        text_indexed = 0
        images_indexed = 0

        # Determine which PDF text to index (deduplicate against PPT)
        unique_pdf_text: list[PageTextContent] = []
        if ppt_slides:
            unique_pdf_text = self._deduplicator.get_unique_pdf_text(
                ppt_slides, pdf_result.pages
            )
        else:
            # No PPT slides provided - index all PDF text
            unique_pdf_text = [
                PageTextContent(
                    document_id=p.document_id,
                    filename=p.filename,
                    page_number=p.page_number,
                    text_content=p.text_content,
                )
                for p in pdf_result.pages
                if p.text_content.strip()
            ]

        # Index unique PDF text
        for page_text in unique_pdf_text:
            try:
                if not page_text.text_content.strip():
                    continue

                embedding = self.text_embedder.embed(page_text.text_content)

                doc = IndexedTextDocument(
                    content_id=page_text.content_id,
                    document_id=page_text.document_id,
                    filename=page_text.filename,
                    slide_number=page_text.page_number,
                    content_type="text",
                    source="pdf",
                    text_content=page_text.text_content,
                    text_embedding=embedding,
                )

                self.client.index(
                    index=self.index_name,
                    id=doc.content_id,
                    body=doc.to_opensearch_doc(),
                )
                text_indexed += 1

            except Exception as e:
                error_msg = f"Failed to index PDF text page {page_text.page_number}: {e}"
                errors.append(error_msg)
                logger.warning(error_msg)

        # Index images from all PDF pages
        for page in pdf_result.pages:
            if not page.has_image:
                continue

            try:
                # Upload image to S3
                s3_uri = self.s3_store.upload(
                    page.image_bytes,
                    document_id=document_id,
                    page_number=page.page_number,
                )
                page.s3_uri = s3_uri

                # Generate image embedding
                embedding = self.image_embedder.embed_image(page.image_bytes)

                # Create document
                doc = IndexedImageDocument(
                    content_id=page.content_id,
                    document_id=document_id,
                    filename=page.filename,
                    slide_number=page.page_number,
                    image_s3_uri=s3_uri,
                    width_px=page.width_px,
                    height_px=page.height_px,
                    image_embedding=embedding,
                )

                self.client.index(
                    index=self.index_name,
                    id=doc.content_id,
                    body=doc.to_opensearch_doc(),
                )
                images_indexed += 1

            except Exception as e:
                error_msg = f"Failed to index PDF image page {page.page_number}: {e}"
                errors.append(error_msg)
                logger.warning(error_msg)

        logger.info(
            "PDF content indexing complete",
            document_id=document_id,
            text_indexed=text_indexed,
            images_indexed=images_indexed,
            errors=len(errors),
        )

        return IndexingResult(
            document_id=document_id,
            filename=pdf_result.filename,
            text_documents_indexed=text_indexed,
            image_documents_indexed=images_indexed,
            errors=errors,
        )

    def index_full_pipeline(
        self,
        pptx_path: str,
        pdf_path: str,
        document_id: str | None = None,
    ) -> tuple[IndexingResult, IndexingResult]:
        """Run full 2-step indexing pipeline (extracts PPT once).

        Args:
            pptx_path: Path to PPTX file.
            pdf_path: Path to PDF file.
            document_id: Optional document ID.

        Returns:
            Tuple of (ppt_result, pdf_result).
        """
        # Extract PPT once
        ppt_extraction = self._ppt_extractor.extract(pptx_path)
        if document_id:
            ppt_extraction.document_id = document_id
            for s in ppt_extraction.slides:
                s.document_id = document_id

        # Step 1: Index PPT text
        ppt_result = self.index_ppt_slides(ppt_extraction, document_id)

        # Step 2: Index PDF content with deduplication
        pdf_result = self.index_pdf_content(
            pdf_path,
            document_id=ppt_extraction.document_id,
            ppt_slides=ppt_extraction.slides,
        )

        return ppt_result, pdf_result

    def delete_document(self, document_id: str) -> int:
        """Delete all indexed content for a document.

        Args:
            document_id: Document identifier.

        Returns:
            Number of documents deleted.
        """
        # Delete from OpenSearch
        response = self.client.delete_by_query(
            index=self.index_name,
            body={
                "query": {
                    "term": {"document_id": document_id}
                }
            },
        )
        deleted_os = response.get("deleted", 0)

        # Delete images from S3
        deleted_s3 = self.s3_store.delete_document_images(document_id)

        logger.info(
            "Deleted document content",
            document_id=document_id,
            opensearch_deleted=deleted_os,
            s3_deleted=deleted_s3,
        )

        return deleted_os

    def get_document_stats(self, document_id: str) -> dict[str, Any]:
        """Get indexing stats for a document.

        Args:
            document_id: Document identifier.

        Returns:
            Dict with stats (text_count, image_count, etc.).
        """
        response = self.client.search(
            index=self.index_name,
            body={
                "query": {
                    "term": {"document_id": document_id}
                },
                "aggs": {
                    "by_type": {
                        "terms": {"field": "content_type"}
                    },
                    "by_source": {
                        "terms": {"field": "source"}
                    },
                },
                "size": 0,
            },
        )

        type_buckets = response["aggregations"]["by_type"]["buckets"]
        source_buckets = response["aggregations"]["by_source"]["buckets"]

        return {
            "document_id": document_id,
            "total_documents": response["hits"]["total"]["value"],
            "by_type": {b["key"]: b["doc_count"] for b in type_buckets},
            "by_source": {b["key"]: b["doc_count"] for b in source_buckets},
        }
