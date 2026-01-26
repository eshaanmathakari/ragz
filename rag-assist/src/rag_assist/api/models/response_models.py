"""Response models for the API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Source(BaseModel):
    """Source information for citations."""

    chunk_id: str = Field(description="Unique chunk identifier")
    filename: str = Field(description="Source filename")
    week_number: int | None = Field(None, description="Week number")
    page_number: int | None = Field(None, description="Page number (for PDFs)")
    slide_number: int | None = Field(None, description="Slide number (for PPTs)")
    section_title: str | None = Field(None, description="Section title")
    relevance_score: float = Field(description="Relevance score (0-1)")
    snippet: str = Field(description="Text snippet from source")


class AnswerResponse(BaseModel):
    """Response model for question answering."""

    answer_id: str = Field(description="Unique answer identifier")
    question: str = Field(description="The original question")
    answer: str = Field(description="The generated answer")
    sources: list[Source] = Field(default_factory=list, description="Source citations")
    confidence: float = Field(description="Confidence score (0-1)")
    in_scope: bool = Field(description="Whether question was in scope")
    processing_time_ms: int = Field(description="Processing time in milliseconds")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "answer_id": "a1b2c3d4",
                    "question": "What is supervised learning?",
                    "answer": "Supervised learning is a type of machine learning...",
                    "sources": [
                        {
                            "chunk_id": "chunk123",
                            "filename": "intro.pptx",
                            "week_number": 1,
                            "slide_number": 5,
                            "section_title": "Introduction to ML",
                            "relevance_score": 0.95,
                            "snippet": "Supervised learning involves...",
                        }
                    ],
                    "confidence": 0.92,
                    "in_scope": True,
                    "processing_time_ms": 1250,
                }
            ]
        }
    }


class IngestResponse(BaseModel):
    """Response model for ingestion requests."""

    job_id: str = Field(description="Ingestion job identifier")
    status: str = Field(description="Job status (queued, running, completed, failed)")
    documents_queued: int = Field(description="Number of documents queued")
    message: str = Field(description="Status message")


class IngestStatusResponse(BaseModel):
    """Response model for ingestion status check."""

    job_id: str = Field(description="Ingestion job identifier")
    status: str = Field(description="Job status")
    documents_processed: int = Field(default=0, description="Documents processed")
    documents_total: int = Field(default=0, description="Total documents")
    chunks_indexed: int = Field(default=0, description="Chunks indexed")
    errors: list[str] = Field(default_factory=list, description="Error messages")
    started_at: datetime | None = Field(None, description="Job start time")
    completed_at: datetime | None = Field(None, description="Job completion time")


class SearchResultItem(BaseModel):
    """Single search result item."""

    chunk_id: str = Field(description="Chunk identifier")
    score: float = Field(description="Relevance score")
    text: str = Field(description="Chunk text content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")


class SearchResponse(BaseModel):
    """Response model for direct search."""

    query: str = Field(description="Search query")
    results: list[SearchResultItem] = Field(description="Search results")
    total_hits: int = Field(description="Total number of matches")
    query_time_ms: float = Field(description="Query execution time in milliseconds")


class WeekInfo(BaseModel):
    """Information about an indexed week."""

    week_number: int | None = Field(description="Week number (null for non-week folders)")
    module_name: str = Field(description="Module/folder name")
    document_count: int = Field(description="Number of documents")
    chunk_count: int = Field(description="Number of indexed chunks")
    file_types: list[str] = Field(description="File types present")


class WeeksResponse(BaseModel):
    """Response model for listing indexed weeks."""

    weeks: list[WeekInfo] = Field(description="List of indexed weeks/modules")
    total_documents: int = Field(description="Total documents indexed")
    total_chunks: int = Field(description="Total chunks indexed")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(description="Overall health status (healthy, degraded, unhealthy)")
    version: str = Field(description="API version")
    services: dict[str, dict[str, Any]] = Field(description="Individual service health")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "version": "0.1.0",
                    "services": {
                        "opensearch": {"status": "healthy", "document_count": 1500},
                        "bedrock": {"status": "healthy"},
                        "guardrails": {"status": "healthy", "configured": True},
                    },
                }
            ]
        }
    }
