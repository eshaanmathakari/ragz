"""PPT Content Extraction Module - 2-Step Framework.

This module provides a complete framework for extracting, embedding, and
retrieving content from PowerPoint presentations. Run from the folder
containing these files (or add the folder to sys.path).

**Step 1 (PPT Path):** Parse PPTX directly → Extract text → Generate embeddings
**Step 2 (PDF Path):** Parse PDF version → Extract text + images → Generate embeddings

Key Features:
- Text extraction from BOTH PPT and PDF for redundancy
- Duplicate text between PPT and PDF is detected and skipped
- Images from PDF are linked to text by slide_number/page_number
- If image extraction fails, text is still retrievable

Usage (from same folder or with folder on sys.path):
    # Step 1: Extract text from PPTX
    from ppt_text_extractor import PPTXTextExtractor
    ppt_extractor = PPTXTextExtractor()
    ppt_result = ppt_extractor.extract("presentation.pptx")

    # Step 2: Extract content from PDF
    from pdf_content_extractor import PDFContentExtractor
    pdf_extractor = PDFContentExtractor(dpi=150)
    pdf_result = pdf_extractor.extract("presentation.pdf")

    # Deduplicate text
    from text_deduplicator import TextDeduplicator
    deduplicator = TextDeduplicator()
    unique_pdf_text = deduplicator.get_unique_pdf_text(ppt_result.slides, pdf_result.pages)

    # Generate embeddings
    from embedders import CohereTextEmbedder, TitanMultimodalEmbedder
    text_embedder = CohereTextEmbedder()
    image_embedder = TitanMultimodalEmbedder()

    # Index to OpenSearch
    from content_indexer import PPTContentIndexer
    indexer = PPTContentIndexer(
        opensearch_client=client,
        text_embedder=text_embedder,
        image_embedder=image_embedder,
        s3_store=S3ImageStore(bucket="my-bucket"),
    )
    ppt_result = indexer.index_ppt_text("presentation.pptx")
    pdf_result = indexer.index_pdf_content("presentation.pdf", document_id=ppt_result.document_id)

    # Retrieve content
    from content_retriever import PPTContentRetriever
    retriever = PPTContentRetriever(
        opensearch_client=client,
        text_embedder=text_embedder,
        s3_store=s3_store,
    )
    results = retriever.search("What is the architecture?")
"""

# Data models
from models import (
    SlideTextContent,
    PPTExtractionResult,
    PDFPageContent,
    PageTextContent,
    PageImageContent,
    PDFExtractionResult,
    IndexedTextDocument,
    IndexedImageDocument,
    IndexingResult,
    RetrievalResult,
    SlideContent,
)

# S3 storage
from s3_store import S3ImageStore

# Step 1: PPT text extraction
from ppt_text_extractor import PPTXTextExtractor

# Step 2: PDF content extraction
from pdf_content_extractor import PDFContentExtractor

# Text deduplication
from text_deduplicator import TextDeduplicator, get_text_for_indexing

# Embedders
from embedders import (
    CohereTextEmbedder,
    TitanMultimodalEmbedder,
    get_text_embedder,
    get_image_embedder,
)

# Indexing
from content_indexer import PPTContentIndexer, OPENSEARCH_INDEX_MAPPING

# Retrieval
from content_retriever import PPTContentRetriever

__all__ = [
    "SlideTextContent",
    "PPTExtractionResult",
    "PDFPageContent",
    "PageTextContent",
    "PageImageContent",
    "PDFExtractionResult",
    "IndexedTextDocument",
    "IndexedImageDocument",
    "IndexingResult",
    "RetrievalResult",
    "SlideContent",
    "S3ImageStore",
    "PPTXTextExtractor",
    "PDFContentExtractor",
    "TextDeduplicator",
    "get_text_for_indexing",
    "CohereTextEmbedder",
    "TitanMultimodalEmbedder",
    "get_text_embedder",
    "get_image_embedder",
    "PPTContentIndexer",
    "OPENSEARCH_INDEX_MAPPING",
    "PPTContentRetriever",
]
