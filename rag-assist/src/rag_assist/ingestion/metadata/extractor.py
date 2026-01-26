"""Main metadata extractor orchestrating all extraction components."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import structlog

from rag_assist.ingestion.metadata.entity_extractor import EntityExtractor
from rag_assist.ingestion.metadata.keyword_extractor import KeywordExtractor
from rag_assist.ingestion.metadata.topic_classifier import TopicClassifier
from rag_assist.ingestion.models import TextChunk

logger = structlog.get_logger(__name__)


class MetadataExtractor:
    """Orchestrates metadata extraction from text chunks.

    Extracts:
    - Keywords (YAKE)
    - Named entities (spaCy)
    - Topic tags (keyword-based classification)
    """

    def __init__(
        self,
        num_keywords: int = 10,
        max_entities: int = 15,
        max_topics: int = 5,
        max_workers: int = 4,
    ):
        """Initialize metadata extractor.

        Args:
            num_keywords: Number of keywords to extract per chunk.
            max_entities: Maximum entities per chunk.
            max_topics: Maximum topics per chunk.
            max_workers: Thread pool size for parallel processing.
        """
        self.num_keywords = num_keywords
        self.max_entities = max_entities
        self.max_topics = max_topics
        self.max_workers = max_workers

        self.keyword_extractor = KeywordExtractor(num_keywords=num_keywords)
        self.entity_extractor = EntityExtractor()
        self.topic_classifier = TopicClassifier(max_topics=max_topics)

        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def extract(self, chunk: TextChunk) -> TextChunk:
        """Extract metadata for a single chunk.

        Args:
            chunk: Text chunk to enrich with metadata.

        Returns:
            Chunk with updated metadata.
        """
        text = chunk.text

        # Extract keywords
        keywords = self.keyword_extractor.extract(text, self.num_keywords)
        chunk.metadata.keywords = keywords

        # Extract entities
        entities = self.entity_extractor.extract(text, self.max_entities)
        chunk.metadata.entities = entities

        # Classify topics
        topics = self.topic_classifier.classify(text)
        chunk.metadata.topic_tags = topics

        # Infer document intent if not already set
        if not chunk.metadata.document_intent:
            chunk.metadata.document_intent = self.topic_classifier.infer_document_intent(text)

        return chunk

    def extract_batch(self, chunks: list[TextChunk]) -> list[TextChunk]:
        """Extract metadata for multiple chunks.

        Args:
            chunks: List of text chunks.

        Returns:
            List of chunks with updated metadata.
        """
        logger.info(f"Extracting metadata for {len(chunks)} chunks")

        enriched_chunks = []
        for chunk in chunks:
            try:
                enriched = self.extract(chunk)
                enriched_chunks.append(enriched)
            except Exception as e:
                logger.warning(f"Metadata extraction failed for chunk: {str(e)}")
                enriched_chunks.append(chunk)

        logger.info(f"Metadata extraction complete for {len(enriched_chunks)} chunks")
        return enriched_chunks

    async def extract_async(self, chunk: TextChunk) -> TextChunk:
        """Extract metadata asynchronously.

        Args:
            chunk: Text chunk to enrich.

        Returns:
            Chunk with updated metadata.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.extract, chunk)

    async def extract_batch_async(self, chunks: list[TextChunk]) -> list[TextChunk]:
        """Extract metadata for multiple chunks asynchronously.

        Args:
            chunks: List of text chunks.

        Returns:
            List of chunks with updated metadata.
        """
        logger.info(f"Extracting metadata async for {len(chunks)} chunks")

        tasks = [self.extract_async(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched_chunks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Metadata extraction failed: {str(result)}")
                enriched_chunks.append(chunks[i])
            else:
                enriched_chunks.append(result)

        return enriched_chunks

    def get_document_summary_metadata(self, chunks: list[TextChunk]) -> dict:
        """Generate document-level metadata from all chunks.

        Args:
            chunks: All chunks from a document.

        Returns:
            Document-level metadata summary.
        """
        if not chunks:
            return {}

        # Aggregate keywords across all chunks
        all_keywords: dict[str, int] = {}
        for chunk in chunks:
            for kw in chunk.metadata.keywords:
                all_keywords[kw] = all_keywords.get(kw, 0) + 1

        # Get top document-level keywords
        sorted_keywords = sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)
        top_keywords = [kw for kw, _ in sorted_keywords[:20]]

        # Aggregate entities
        all_entities: dict[str, set] = {}
        for chunk in chunks:
            for entity in chunk.metadata.entities:
                entity_type = entity["type"]
                if entity_type not in all_entities:
                    all_entities[entity_type] = set()
                all_entities[entity_type].add(entity["text"])

        # Aggregate topics
        all_topics: dict[str, int] = {}
        for chunk in chunks:
            for topic in chunk.metadata.topic_tags:
                all_topics[topic] = all_topics.get(topic, 0) + 1

        sorted_topics = sorted(all_topics.items(), key=lambda x: x[1], reverse=True)
        top_topics = [topic for topic, _ in sorted_topics[:10]]

        # Determine primary intent
        intent_counts: dict[str, int] = {}
        for chunk in chunks:
            intent = chunk.metadata.document_intent
            if intent:
                intent_counts[intent] = intent_counts.get(intent, 0) + 1

        primary_intent = max(intent_counts, key=intent_counts.get) if intent_counts else "unknown"

        return {
            "top_keywords": top_keywords,
            "entities_by_type": {k: list(v) for k, v in all_entities.items()},
            "top_topics": top_topics,
            "primary_intent": primary_intent,
            "total_chunks": len(chunks),
        }

    def close(self) -> None:
        """Cleanup resources."""
        self._executor.shutdown(wait=False)
