"""Request models for the API."""

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    """Request model for asking questions."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The question to ask about course materials",
    )
    week_filter: int | None = Field(
        None,
        ge=1,
        le=52,
        description="Optional week number to filter content",
    )
    conversation_id: str | None = Field(
        None,
        description="Optional conversation ID for multi-turn conversations",
    )
    include_sources: bool = Field(
        True,
        description="Include source information in response",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "question": "What is supervised learning?",
                    "week_filter": 1,
                    "include_sources": True,
                }
            ]
        }
    }


class IngestRequest(BaseModel):
    """Request model for triggering document ingestion."""

    week_number: int | None = Field(
        None,
        ge=1,
        description="Week number to ingest (None for all)",
    )
    s3_prefix: str = Field(
        ...,
        description="S3 prefix path for documents to ingest",
    )
    force_reprocess: bool = Field(
        False,
        description="Force reprocessing of already-indexed documents",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "week_number": 1,
                    "s3_prefix": "data/week 1/",
                    "force_reprocess": False,
                }
            ]
        }
    }


class SearchRequest(BaseModel):
    """Request model for direct search (admin/debug)."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query",
    )
    top_k: int = Field(
        10,
        ge=1,
        le=50,
        description="Number of results to return",
    )
    week_filter: int | None = Field(
        None,
        ge=1,
        description="Optional week filter",
    )
    file_type_filter: str | None = Field(
        None,
        description="Optional file type filter (pdf, pptx, docx)",
    )
    search_type: str = Field(
        "hybrid",
        description="Search type: hybrid, vector, or keyword",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "machine learning algorithms",
                    "top_k": 5,
                    "search_type": "hybrid",
                }
            ]
        }
    }
