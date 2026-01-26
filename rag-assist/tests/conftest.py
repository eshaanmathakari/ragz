"""Pytest configuration and fixtures."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set test environment before importing application code
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["OPENSEARCH_ENDPOINT"] = "http://localhost:9200"
os.environ["S3_BUCKET_NAME"] = "test-bucket"


@pytest.fixture
def sample_text():
    """Sample text for testing."""
    return """Machine learning is a subset of artificial intelligence.

It enables systems to learn and improve from experience without being explicitly programmed.

Supervised learning uses labeled data to train models.
Unsupervised learning finds patterns in unlabeled data.
Reinforcement learning learns through trial and error."""


@pytest.fixture
def sample_pptx_content():
    """Mock parsed PPTX content."""
    from rag_assist.ingestion.models import (
        DocumentMetadata,
        DocumentType,
        ParsedDocument,
        SlideContent,
    )

    slides = [
        SlideContent(
            slide_number=1,
            title="Introduction to ML",
            text="Machine learning is a subset of AI that enables systems to learn.",
            notes="Speaker notes for slide 1",
            layout_type="title",
        ),
        SlideContent(
            slide_number=2,
            title="Supervised Learning",
            text="Supervised learning uses labeled data. Examples include classification and regression.",
            notes="",
            layout_type="content",
        ),
        SlideContent(
            slide_number=3,
            title="Unsupervised Learning",
            text="Unsupervised learning works with unlabeled data. Clustering is a common technique.",
            notes="",
            layout_type="content",
        ),
    ]

    metadata = DocumentMetadata(
        filename="test_presentation.pptx",
        file_type=DocumentType.PPTX,
        s3_uri="s3://test-bucket/week 1/test_presentation.pptx",
        file_size=1024,
        total_slides=3,
    )

    return ParsedDocument(
        content=slides,
        metadata=metadata,
        raw_text="",
    )


@pytest.fixture
def sample_pdf_content():
    """Mock parsed PDF content."""
    from rag_assist.ingestion.models import (
        DocumentMetadata,
        DocumentType,
        PageContent,
        ParsedDocument,
        TextBlock,
    )

    pages = [
        PageContent(
            page_number=1,
            text="Neural networks are computing systems inspired by biological neural networks.",
            text_blocks=[
                TextBlock(
                    text="Neural Network Architecture",
                    font_size=18,
                    is_heading=True,
                ),
                TextBlock(
                    text="Neural networks are computing systems inspired by biological neural networks.",
                    font_size=12,
                    is_heading=False,
                ),
            ],
        ),
        PageContent(
            page_number=2,
            text="Deep learning uses neural networks with many layers to learn complex patterns.",
            text_blocks=[
                TextBlock(
                    text="Deep learning uses neural networks with many layers.",
                    font_size=12,
                    is_heading=False,
                ),
            ],
        ),
    ]

    metadata = DocumentMetadata(
        filename="neural_networks.pdf",
        file_type=DocumentType.PDF,
        s3_uri="s3://test-bucket/week 2/neural_networks.pdf",
        file_size=2048,
        total_pages=2,
    )

    return ParsedDocument(
        content=pages,
        metadata=metadata,
        raw_text="",
    )


@pytest.fixture
def sample_chunks():
    """Sample text chunks for testing."""
    from rag_assist.ingestion.models import ChunkMetadata, TextChunk

    return [
        TextChunk(
            text="Machine learning is a subset of artificial intelligence.",
            metadata=ChunkMetadata(
                chunk_id="chunk_001",
                document_id="doc_001",
                filename="intro.pptx",
                file_type="pptx",
                s3_uri="s3://bucket/week 1/intro.pptx",
                week_number=1,
                slide_number=1,
                content_hash="hash_001",
            ),
        ),
        TextChunk(
            text="Machine learning is a branch of artificial intelligence.",
            metadata=ChunkMetadata(
                chunk_id="chunk_002",
                document_id="doc_001",
                filename="intro.pptx",
                file_type="pptx",
                s3_uri="s3://bucket/week 1/intro.pptx",
                week_number=1,
                slide_number=2,
                content_hash="hash_002",
            ),
        ),
        TextChunk(
            text="Neural networks are computational models inspired by the brain.",
            metadata=ChunkMetadata(
                chunk_id="chunk_003",
                document_id="doc_002",
                filename="neural.pdf",
                file_type="pdf",
                s3_uri="s3://bucket/week 2/neural.pdf",
                week_number=2,
                page_number=1,
                content_hash="hash_003",
            ),
        ),
    ]


@pytest.fixture
def mock_opensearch_client():
    """Mock OpenSearch client."""
    client = MagicMock()
    client.indices.exists.return_value = True
    client.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {
                    "_id": "chunk_001",
                    "_score": 0.95,
                    "_source": {
                        "text": "Machine learning is a subset of AI.",
                        "filename": "intro.pptx",
                        "week_number": 1,
                    },
                },
                {
                    "_id": "chunk_002",
                    "_score": 0.85,
                    "_source": {
                        "text": "Supervised learning uses labeled data.",
                        "filename": "intro.pptx",
                        "week_number": 1,
                    },
                },
            ],
        }
    }
    return client


@pytest.fixture
def mock_bedrock_client():
    """Mock Bedrock client for embeddings."""
    client = MagicMock()
    client.invoke_model.return_value = {
        "body": MagicMock(
            read=MagicMock(
                return_value=b'{"embedding": [0.1, 0.2, 0.3]}'
            )
        )
    }
    return client
