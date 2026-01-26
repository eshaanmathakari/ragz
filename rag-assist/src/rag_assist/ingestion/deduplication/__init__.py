"""Deduplication strategies for text chunks."""

from rag_assist.ingestion.deduplication.hash_dedup import HashDeduplicator
from rag_assist.ingestion.deduplication.semantic_dedup import SemanticDeduplicator
from rag_assist.ingestion.deduplication.dedup_manager import DeduplicationManager

__all__ = [
    "HashDeduplicator",
    "SemanticDeduplicator",
    "DeduplicationManager",
]
