"""Retrieval tool for searching course materials."""

from typing import Annotated, Any

import structlog

from rag_assist.config.settings import get_settings
from rag_assist.ingestion.deduplication import DeduplicationManager
from rag_assist.vectorstore.hybrid_search import HybridSearcher, SearchResult

logger = structlog.get_logger(__name__)

# Global instances (initialized on first use)
_searcher: HybridSearcher | None = None
_dedup_manager: DeduplicationManager | None = None


def get_searcher() -> HybridSearcher:
    """Get or create hybrid searcher instance."""
    global _searcher
    if _searcher is None:
        _searcher = HybridSearcher()
    return _searcher


def get_dedup_manager() -> DeduplicationManager:
    """Get or create deduplication manager instance."""
    global _dedup_manager
    if _dedup_manager is None:
        _dedup_manager = DeduplicationManager()
    return _dedup_manager


def retrieve_content(
    query: Annotated[str, "The search query to find relevant content from course materials"],
    week_filter: Annotated[int | None, "Optional week number to filter by (1, 2, 3, etc.)"] = None,
    file_type_filter: Annotated[
        str | None, "Optional file type filter (pdf, pptx, docx)"
    ] = None,
    top_k: Annotated[int, "Number of results to retrieve"] = 10,
) -> str:
    """Search the indexed course materials for content relevant to the query.

    This tool searches through all indexed documents (PDFs, PowerPoints, Word docs)
    and returns the most relevant text chunks with source information for citations.

    Args:
        query: The search query describing what information to find.
        week_filter: Optional week number to limit search to specific week's content.
        file_type_filter: Optional filter by document type (pdf, pptx, docx).
        top_k: Number of results to retrieve (default 10).

    Returns:
        Formatted string containing relevant content with source information.
    """
    settings = get_settings()
    searcher = get_searcher()
    dedup_manager = get_dedup_manager()

    # Build filters
    filters: dict[str, Any] = {}
    if week_filter is not None:
        filters["week_number"] = week_filter
    if file_type_filter:
        filters["file_type"] = file_type_filter.lower()

    # Execute search
    logger.info(
        "Executing retrieval",
        query=query[:100],
        filters=filters,
        top_k=top_k,
    )

    # Get more results initially for deduplication
    search_response = searcher.search(
        query=query,
        top_k=top_k * 2,
        filters=filters if filters else None,
    )

    if not search_response.results:
        return "No relevant content found in the course materials for this query."

    # Convert to TextChunks for deduplication
    chunks = [result.to_text_chunk() for result in search_response.results]

    # Deduplicate at query time
    deduped_chunks = dedup_manager.deduplicate_query_results(
        chunks=chunks,
        similarity_threshold=settings.rag.similarity_threshold,
        max_chunks=top_k,
    )

    # Format results for the LLM
    formatted_results = _format_search_results(deduped_chunks, search_response.results)

    logger.info(
        "Retrieval complete",
        original_results=len(search_response.results),
        after_dedup=len(deduped_chunks),
    )

    return formatted_results


def _format_search_results(
    chunks: list,
    original_results: list[SearchResult],
) -> str:
    """Format search results for LLM consumption.

    Args:
        chunks: Deduplicated TextChunks.
        original_results: Original search results with scores.

    Returns:
        Formatted string with content and sources.
    """
    # Create score lookup
    score_lookup = {r.chunk_id: r.score for r in original_results}

    formatted_parts = []
    formatted_parts.append("=== RETRIEVED CONTENT ===\n")

    for i, chunk in enumerate(chunks, 1):
        meta = chunk.metadata
        score = score_lookup.get(meta.chunk_id, 0.0)

        # Build source citation
        source_parts = []
        if meta.module_name:
            source_parts.append(meta.module_name)
        if meta.week_number:
            source_parts.append(f"Week {meta.week_number}")
        if meta.slide_number:
            source_parts.append(f"Slide {meta.slide_number}")
        elif meta.page_number:
            source_parts.append(f"Page {meta.page_number}")
        if meta.filename:
            source_parts.append(meta.filename)

        source_str = " | ".join(source_parts) if source_parts else "Unknown source"

        # Add section title if available
        section_str = ""
        if meta.section_title:
            section_str = f"\nSection: {meta.section_title}"

        formatted_parts.append(
            f"--- Result {i} (relevance: {score:.2f}) ---\n"
            f"Source: [{source_str}]{section_str}\n\n"
            f"{chunk.text}\n"
        )

    formatted_parts.append("\n=== END RETRIEVED CONTENT ===")

    return "\n".join(formatted_parts)


# Tool function with proper annotation for Strands
retrieve_content.__doc__ = """Search the indexed course materials for content relevant to the query.

This tool searches through all indexed documents (PDFs, PowerPoints, Word docs)
and returns the most relevant text chunks with source information for citations.

Use this tool when you need to:
- Answer questions about course content
- Find specific information from lectures or readings
- Look up definitions, concepts, or examples from the materials

The results include source information (week, slide/page, filename) that you
should use to cite your answers."""
