"""Scope checker tool for validating question relevance."""

from typing import Annotated

import structlog

from rag_assist.vectorstore.hybrid_search import HybridSearcher

logger = structlog.get_logger(__name__)

# Global searcher instance
_searcher: HybridSearcher | None = None


def get_searcher() -> HybridSearcher:
    """Get or create hybrid searcher instance."""
    global _searcher
    if _searcher is None:
        _searcher = HybridSearcher()
    return _searcher


# Keywords that indicate out-of-scope questions
OUT_OF_SCOPE_KEYWORDS = {
    # General knowledge
    "weather", "temperature", "forecast",
    "news", "current events", "politics",
    "sports", "game", "match", "score",
    "movie", "film", "tv show", "celebrity",
    "recipe", "cooking", "food",
    # Coding assistance
    "write code", "write a program", "debug", "fix my code",
    "implement", "coding", "programming", "algorithm",
    "python code", "javascript", "java code",
    # Personal advice
    "relationship", "dating", "love advice",
    "career advice", "job", "salary",
    "health advice", "medical", "symptoms",
    "financial advice", "investment",
    "life advice", "personal problem",
    # Harmful/jailbreak
    "ignore previous", "ignore instructions",
    "pretend", "roleplay", "act as",
    "bypass", "hack", "exploit",
    "harmful", "illegal", "dangerous",
}

# Topics that are clearly in-scope (boost confidence)
IN_SCOPE_INDICATORS = {
    "slide", "page", "lecture", "chapter",
    "week", "module", "lesson", "topic",
    "explain", "what is", "define", "describe",
    "example", "concept", "theory",
    "course", "material", "content",
}


def check_scope(
    question: Annotated[str, "The user's question to validate"],
) -> dict:
    """Check if a question is within the scope of indexed course materials.

    This tool performs a quick check to determine if the question is likely
    to be answerable from the course materials. Use this BEFORE retrieving
    content to avoid wasting resources on out-of-scope questions.

    Args:
        question: The user's question to validate.

    Returns:
        Dictionary with:
        - in_scope: Boolean indicating if question is in scope
        - confidence: Confidence score (0-1)
        - reason: Explanation of the decision
        - related_topics: List of potentially related topics from materials
    """
    question_lower = question.lower()

    # Check for explicit out-of-scope keywords
    for keyword in OUT_OF_SCOPE_KEYWORDS:
        if keyword in question_lower:
            logger.info(f"Question blocked by keyword: {keyword}")
            return {
                "in_scope": False,
                "confidence": 0.9,
                "reason": f"Question appears to be about {keyword}, which is outside the course materials.",
                "related_topics": [],
                "blocked_category": _categorize_blocked(keyword),
            }

    # Check for in-scope indicators
    has_in_scope_indicator = any(ind in question_lower for ind in IN_SCOPE_INDICATORS)

    # Quick semantic search to check relevance
    searcher = get_searcher()
    try:
        search_response = searcher.search(
            query=question,
            top_k=3,
        )

        if not search_response.results:
            # No results at all
            return {
                "in_scope": False,
                "confidence": 0.7,
                "reason": "No relevant content found in the course materials for this question.",
                "related_topics": [],
            }

        # Check relevance scores
        max_score = max(r.score for r in search_response.results)
        avg_score = sum(r.score for r in search_response.results) / len(search_response.results)

        # Extract related topics from results
        related_topics = set()
        for result in search_response.results:
            topics = result.metadata.get("topic_tags", [])
            related_topics.update(topics[:2])

        # Determine if in scope based on scores
        # Higher threshold if no in-scope indicators found
        threshold = 0.3 if has_in_scope_indicator else 0.5

        if max_score >= threshold:
            confidence = min(max_score, 1.0)
            return {
                "in_scope": True,
                "confidence": confidence,
                "reason": "Question appears to be related to indexed course materials.",
                "related_topics": list(related_topics)[:5],
                "relevance_score": max_score,
            }
        else:
            return {
                "in_scope": False,
                "confidence": 1.0 - max_score,
                "reason": "Question does not appear to be covered in the available course materials.",
                "related_topics": list(related_topics)[:5],
                "relevance_score": max_score,
            }

    except Exception as e:
        logger.error(f"Scope check failed: {str(e)}")
        # On error, be permissive and let retrieval handle it
        return {
            "in_scope": True,
            "confidence": 0.5,
            "reason": "Unable to verify scope, proceeding with retrieval.",
            "related_topics": [],
            "error": str(e),
        }


def _categorize_blocked(keyword: str) -> str:
    """Categorize the type of blocked content.

    Args:
        keyword: The keyword that triggered the block.

    Returns:
        Category string.
    """
    general_knowledge = {"weather", "temperature", "forecast", "news", "current events",
                        "politics", "sports", "game", "match", "score", "movie", "film",
                        "tv show", "celebrity", "recipe", "cooking", "food"}

    coding = {"write code", "write a program", "debug", "fix my code", "implement",
             "coding", "programming", "algorithm", "python code", "javascript", "java code"}

    personal = {"relationship", "dating", "love advice", "career advice", "job",
               "salary", "health advice", "medical", "symptoms", "financial advice",
               "investment", "life advice", "personal problem"}

    harmful = {"ignore previous", "ignore instructions", "pretend", "roleplay",
              "act as", "bypass", "hack", "exploit", "harmful", "illegal", "dangerous"}

    if keyword in general_knowledge:
        return "general_knowledge"
    elif keyword in coding:
        return "coding_assistance"
    elif keyword in personal:
        return "personal_advice"
    elif keyword in harmful:
        return "harmful_content"
    else:
        return "other"


# Tool docstring for Strands
check_scope.__doc__ = """Check if a question is within the scope of indexed course materials.

This tool performs a quick check to determine if the question is likely
to be answerable from the course materials.

Use this BEFORE retrieving content when:
- The question seems potentially off-topic
- You want to provide a helpful refusal for out-of-scope questions
- You need to determine if retrieval is worth attempting

The tool blocks questions about:
- General knowledge (weather, news, sports, entertainment)
- Coding assistance (writing/debugging code)
- Personal advice (career, relationships, health)
- Harmful content (jailbreaks, exploits, illegal activities)"""
