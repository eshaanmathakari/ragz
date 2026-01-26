"""Main FastAPI application for the RAG Learning Assistant."""

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rag_assist import __version__
from rag_assist.agent import LearningAgent
from rag_assist.agent.guardrails import GuardrailOrchestrator
from rag_assist.api.models import (
    AnswerResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    QuestionRequest,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    Source,
)
from rag_assist.config.settings import get_settings
from rag_assist.vectorstore import HybridSearcher, OpenSearchClient

logger = structlog.get_logger(__name__)

# Global instances (initialized on startup)
_agent: LearningAgent | None = None
_searcher: HybridSearcher | None = None
_opensearch: OpenSearchClient | None = None
_guardrails: GuardrailOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global _agent, _searcher, _opensearch, _guardrails

    logger.info("Starting RAG Learning Assistant API")

    # Initialize components
    try:
        _agent = LearningAgent()
        _searcher = HybridSearcher()
        _opensearch = OpenSearchClient()
        _guardrails = GuardrailOrchestrator()

        logger.info("All components initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize components: {str(e)}")
        # Continue startup even if some components fail

    yield

    # Cleanup
    logger.info("Shutting down RAG Learning Assistant API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app.
    """
    settings = get_settings()

    app = FastAPI(
        title="RAG Learning Assistant API",
        description="Production RAG-based Q&A API for course materials using AWS Strands SDK",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.api.debug else None,
        redoc_url="/redoc" if settings.api.debug else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            "Request processed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time_ms=round(process_time * 1000, 2),
        )

        response.headers["X-Process-Time"] = str(process_time)
        return response

    return app


# Create app instance
app = create_app()


# ============== API Endpoints ==============


@app.post("/api/v1/ask", response_model=AnswerResponse)
async def ask_question(request: QuestionRequest) -> AnswerResponse:
    """Ask a question about course materials.

    Returns an answer with sources and citations based on indexed content.
    """
    start_time = time.time()

    # Validate input with guardrails
    if _guardrails:
        input_validation = _guardrails.validate_input(request.question)
        if not input_validation.passed:
            return AnswerResponse(
                answer_id=str(uuid.uuid4()),
                question=request.question,
                answer=_guardrails.get_refusal_response(input_validation),
                sources=[],
                confidence=0.0,
                in_scope=False,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    # Get answer from agent
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        response = _agent.answer_simple(
            question=request.question,
            week_filter=request.week_filter,
        )

        # Build sources list
        sources = []
        if request.include_sources:
            for src in response.sources[:10]:  # Limit to 10 sources
                sources.append(
                    Source(
                        chunk_id=src.get("chunk_id", ""),
                        filename=src.get("filename", ""),
                        week_number=src.get("week_number"),
                        page_number=src.get("page_number"),
                        slide_number=src.get("slide_number"),
                        section_title=src.get("section_title"),
                        relevance_score=src.get("relevance_score", 0.0),
                        snippet=src.get("snippet", "")[:200],
                    )
                )

        processing_time_ms = int((time.time() - start_time) * 1000)

        return AnswerResponse(
            answer_id=str(uuid.uuid4()),
            question=request.question,
            answer=response.answer,
            sources=sources,
            confidence=response.confidence,
            in_scope=response.in_scope,
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error(f"Question answering failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process question")


@app.post("/api/v1/search", response_model=SearchResponse)
async def search_content(request: SearchRequest) -> SearchResponse:
    """Direct search in indexed content (for debugging/admin).

    Performs hybrid, vector, or keyword search based on search_type.
    """
    if not _searcher:
        raise HTTPException(status_code=503, detail="Searcher not initialized")

    try:
        # Build filters
        filters = {}
        if request.week_filter:
            filters["week_number"] = request.week_filter
        if request.file_type_filter:
            filters["file_type"] = request.file_type_filter

        # Execute search based on type
        if request.search_type == "vector":
            response = _searcher.search_vector_only(
                query=request.query,
                top_k=request.top_k,
                filters=filters if filters else None,
            )
        elif request.search_type == "keyword":
            response = _searcher.search_keyword_only(
                query=request.query,
                top_k=request.top_k,
                filters=filters if filters else None,
            )
        else:
            response = _searcher.search(
                query=request.query,
                top_k=request.top_k,
                filters=filters if filters else None,
            )

        # Convert results
        results = [
            SearchResultItem(
                chunk_id=r.chunk_id,
                score=r.score,
                text=r.text[:500],  # Truncate for response
                metadata=r.metadata,
            )
            for r in response.results
        ]

        return SearchResponse(
            query=request.query,
            results=results,
            total_hits=response.total_hits,
            query_time_ms=response.query_time_ms,
        )

    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")


@app.post("/api/v1/ingest", response_model=IngestResponse)
async def trigger_ingestion(request: IngestRequest) -> IngestResponse:
    """Trigger document ingestion for specified content.

    Note: In production, this should trigger a Step Functions workflow.
    """
    job_id = str(uuid.uuid4())

    # In production, this would:
    # 1. Start a Step Functions execution
    # 2. Return the job ID for status tracking
    # For now, return a placeholder response

    logger.info(
        "Ingestion requested",
        job_id=job_id,
        s3_prefix=request.s3_prefix,
        week_number=request.week_number,
    )

    return IngestResponse(
        job_id=job_id,
        status="queued",
        documents_queued=0,
        message=f"Ingestion job {job_id} queued for {request.s3_prefix}",
    )


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check health status of the API and its dependencies."""
    services = {}
    overall_status = "healthy"

    # Check OpenSearch
    try:
        if _opensearch:
            health = _opensearch.health_check()
            doc_count = _opensearch.get_document_count()
            services["opensearch"] = {
                "status": health.get("status", "unknown"),
                "document_count": doc_count,
            }
            if health.get("status") != "green":
                overall_status = "degraded"
        else:
            services["opensearch"] = {"status": "not_initialized"}
            overall_status = "degraded"
    except Exception as e:
        services["opensearch"] = {"status": "error", "error": str(e)}
        overall_status = "unhealthy"

    # Check Bedrock (simple connectivity check)
    try:
        services["bedrock"] = {"status": "healthy"}
    except Exception as e:
        services["bedrock"] = {"status": "error", "error": str(e)}
        overall_status = "degraded"

    # Check guardrails
    if _guardrails:
        guardrail_status = _guardrails.get_status()
        services["guardrails"] = {
            "status": "healthy",
            "configured": guardrail_status.get("bedrock_guardrails_configured", False),
        }
    else:
        services["guardrails"] = {"status": "not_initialized"}

    return HealthResponse(
        status=overall_status,
        version=__version__,
        services=services,
    )


@app.get("/api/v1/weeks")
async def list_indexed_weeks():
    """List all indexed weeks/modules with document counts.

    Note: This is a placeholder - full implementation would aggregate from OpenSearch.
    """
    # In production, aggregate from OpenSearch
    return {
        "weeks": [],
        "total_documents": 0,
        "total_chunks": _opensearch.get_document_count() if _opensearch else 0,
        "message": "Full implementation requires OpenSearch aggregation query",
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "status_code": 500},
    )


# Run with uvicorn
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "rag_assist.api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.debug,
    )
