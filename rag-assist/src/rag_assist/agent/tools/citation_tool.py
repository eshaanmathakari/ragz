"""Citation formatting tool for adding proper source references."""

from typing import Annotated

import structlog

logger = structlog.get_logger(__name__)


def format_citations(
    answer_text: Annotated[str, "The answer text that needs citations"],
    sources: Annotated[
        list[dict],
        "List of source dictionaries with keys: week_number, slide_number, page_number, filename, section_title"
    ],
) -> str:
    """Format citations in the answer text with proper source references.

    This tool takes an answer and its sources and produces a properly
    cited response. Use this after generating an answer to ensure
    proper attribution of information.

    Args:
        answer_text: The answer text to add citations to.
        sources: List of source dictionaries containing:
            - week_number: Week number (if available)
            - slide_number: Slide number for presentations
            - page_number: Page number for PDFs/docs
            - filename: Source filename
            - section_title: Section title (if available)
            - snippet: Brief snippet of the source content

    Returns:
        Formatted answer with a Sources section.
    """
    if not sources:
        return answer_text + "\n\n*Note: Unable to determine specific sources for this answer.*"

    # Build citations
    citations = []
    seen_citations = set()  # Deduplicate

    for i, source in enumerate(sources, 1):
        citation = _build_citation(source)

        # Skip duplicates
        if citation in seen_citations:
            continue
        seen_citations.add(citation)

        citations.append(f"[{len(citations) + 1}] {citation}")

    # Format sources section
    sources_section = "\n\n**Sources:**\n" + "\n".join(citations)

    return answer_text + sources_section


def _build_citation(source: dict) -> str:
    """Build a single citation string from source metadata.

    Args:
        source: Source dictionary.

    Returns:
        Formatted citation string.
    """
    parts = []

    # Week information
    week = source.get("week_number")
    if week is not None:
        parts.append(f"Week {week}")

    # Location in document
    slide = source.get("slide_number")
    page = source.get("page_number")
    if slide is not None:
        parts.append(f"Slide {slide}")
    elif page is not None:
        parts.append(f"Page {page}")

    # Filename
    filename = source.get("filename")
    if filename:
        parts.append(f"'{filename}'")

    # Section title
    section = source.get("section_title")
    if section:
        parts.append(f"- {section}")

    if parts:
        return " | ".join(parts)
    else:
        return "Unknown source"


def create_inline_citation(
    week_number: int | None = None,
    slide_number: int | None = None,
    page_number: int | None = None,
) -> str:
    """Create an inline citation marker.

    Args:
        week_number: Week number.
        slide_number: Slide number.
        page_number: Page number.

    Returns:
        Inline citation string like "[Week 1, Slide 5]".
    """
    parts = []

    if week_number is not None:
        parts.append(f"Week {week_number}")

    if slide_number is not None:
        parts.append(f"Slide {slide_number}")
    elif page_number is not None:
        parts.append(f"Page {page_number}")

    if parts:
        return f"[{', '.join(parts)}]"
    else:
        return "[Source]"


def extract_sources_from_context(context: str) -> list[dict]:
    """Extract source information from retrieved context.

    This parses the formatted context returned by retrieve_content
    to extract source metadata for citation.

    Args:
        context: Retrieved context string from retrieve_content.

    Returns:
        List of source dictionaries.
    """
    import re

    sources = []

    # Pattern to match source lines like "Source: [Week 1 | Slide 5 | file.pptx]"
    source_pattern = re.compile(
        r"Source:\s*\[([^\]]+)\]",
        re.IGNORECASE
    )

    for match in source_pattern.finditer(context):
        source_str = match.group(1)
        source_dict = _parse_source_string(source_str)
        if source_dict:
            sources.append(source_dict)

    return sources


def _parse_source_string(source_str: str) -> dict | None:
    """Parse a source string into a dictionary.

    Args:
        source_str: Source string like "Week 1 | Slide 5 | file.pptx".

    Returns:
        Parsed source dictionary or None.
    """
    import re

    parts = [p.strip() for p in source_str.split("|")]
    source = {}

    for part in parts:
        # Week number
        week_match = re.search(r"Week\s+(\d+)", part, re.IGNORECASE)
        if week_match:
            source["week_number"] = int(week_match.group(1))
            continue

        # Slide number
        slide_match = re.search(r"Slide\s+(\d+)", part, re.IGNORECASE)
        if slide_match:
            source["slide_number"] = int(slide_match.group(1))
            continue

        # Page number
        page_match = re.search(r"Page\s+(\d+)", part, re.IGNORECASE)
        if page_match:
            source["page_number"] = int(page_match.group(1))
            continue

        # Filename (anything with an extension)
        if "." in part and not any(x in part.lower() for x in ["week", "slide", "page"]):
            source["filename"] = part

    return source if source else None


# Tool docstring for Strands
format_citations.__doc__ = """Format citations in the answer text with proper source references.

This tool takes an answer and its sources and produces a properly
cited response with a Sources section at the end.

Use this after generating an answer to ensure proper attribution.

Example output:
---
[Your answer here explaining the concept...]

**Sources:**
[1] Week 1 | Slide 5 | 'intro.pptx' - Introduction to Concepts
[2] Week 2 | Page 12 | 'chapter2.pdf' - Advanced Topics
---"""
