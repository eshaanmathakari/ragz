"""Topic classification for document content."""

import re
from collections import Counter

import structlog

logger = structlog.get_logger(__name__)


class TopicClassifier:
    """Classify text into topics using keyword-based heuristics.

    For production, this can be enhanced with:
    - LLM-based classification (once per document)
    - Pre-trained topic models
    - Custom fine-tuned classifiers
    """

    # Default topic keywords (can be customized per use case)
    DEFAULT_TOPIC_KEYWORDS: dict[str, list[str]] = {
        "introduction": ["introduction", "overview", "getting started", "basics", "fundamentals"],
        "concepts": ["concept", "theory", "principle", "definition", "terminology"],
        "tutorial": ["tutorial", "how to", "step by step", "guide", "walkthrough", "example"],
        "reference": ["reference", "api", "documentation", "specification", "syntax"],
        "best_practices": ["best practice", "recommendation", "tip", "guideline", "pattern"],
        "troubleshooting": ["troubleshoot", "debug", "error", "issue", "problem", "fix"],
        "architecture": ["architecture", "design", "structure", "component", "system"],
        "security": ["security", "authentication", "authorization", "encryption", "vulnerability"],
        "performance": ["performance", "optimization", "speed", "efficiency", "scalability"],
        "testing": ["test", "testing", "unit test", "integration", "validation"],
        "deployment": ["deploy", "deployment", "production", "release", "ci/cd"],
        "data": ["data", "database", "storage", "query", "model"],
        "networking": ["network", "api", "http", "request", "endpoint"],
        "configuration": ["config", "configuration", "setting", "environment", "setup"],
    }

    def __init__(
        self,
        topic_keywords: dict[str, list[str]] | None = None,
        threshold: float = 0.01,
        max_topics: int = 5,
    ):
        """Initialize topic classifier.

        Args:
            topic_keywords: Custom mapping of topics to keywords.
            threshold: Minimum keyword frequency to assign topic.
            max_topics: Maximum number of topics to assign.
        """
        self.topic_keywords = topic_keywords or self.DEFAULT_TOPIC_KEYWORDS
        self.threshold = threshold
        self.max_topics = max_topics

        # Build reverse index for faster lookup
        self._keyword_to_topics = self._build_keyword_index()

    def _build_keyword_index(self) -> dict[str, list[str]]:
        """Build reverse index from keywords to topics.

        Returns:
            Dictionary mapping keywords to list of topics.
        """
        index: dict[str, list[str]] = {}
        for topic, keywords in self.topic_keywords.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in index:
                    index[keyword_lower] = []
                index[keyword_lower].append(topic)
        return index

    def classify(self, text: str) -> list[str]:
        """Classify text into topics.

        Args:
            text: Text to classify.

        Returns:
            List of assigned topic tags.
        """
        if not text or not text.strip():
            return []

        text_lower = text.lower()
        word_count = len(text_lower.split())

        if word_count == 0:
            return []

        # Count topic matches
        topic_scores: Counter = Counter()

        for keyword, topics in self._keyword_to_topics.items():
            # Count keyword occurrences
            count = len(re.findall(rf"\b{re.escape(keyword)}\b", text_lower))
            if count > 0:
                for topic in topics:
                    topic_scores[topic] += count

        if not topic_scores:
            return []

        # Normalize by word count and filter by threshold
        topics = []
        for topic, count in topic_scores.most_common():
            score = count / word_count
            if score >= self.threshold:
                topics.append(topic)
            if len(topics) >= self.max_topics:
                break

        return topics

    def classify_with_scores(self, text: str) -> list[tuple[str, float]]:
        """Classify text with confidence scores.

        Args:
            text: Text to classify.

        Returns:
            List of (topic, score) tuples.
        """
        if not text or not text.strip():
            return []

        text_lower = text.lower()
        word_count = len(text_lower.split())

        if word_count == 0:
            return []

        topic_scores: Counter = Counter()

        for keyword, topics in self._keyword_to_topics.items():
            count = len(re.findall(rf"\b{re.escape(keyword)}\b", text_lower))
            if count > 0:
                for topic in topics:
                    topic_scores[topic] += count

        # Normalize and return
        results = []
        for topic, count in topic_scores.most_common(self.max_topics):
            score = count / word_count
            if score >= self.threshold:
                results.append((topic, score))

        return results

    def classify_batch(self, texts: list[str]) -> list[list[str]]:
        """Classify multiple texts.

        Args:
            texts: List of texts to classify.

        Returns:
            List of topic lists.
        """
        return [self.classify(text) for text in texts]

    def add_topic(self, topic: str, keywords: list[str]) -> None:
        """Add a new topic with keywords.

        Args:
            topic: Topic name.
            keywords: List of keywords for the topic.
        """
        self.topic_keywords[topic] = keywords
        self._keyword_to_topics = self._build_keyword_index()

    def infer_document_intent(self, text: str) -> str:
        """Infer the intent/purpose of a document.

        Args:
            text: Document text (full or summary).

        Returns:
            Intent string: 'overview', 'tutorial', 'reference', or 'unknown'.
        """
        text_lower = text.lower()

        # Check for tutorial indicators
        tutorial_indicators = [
            "step 1", "step 2", "how to", "let's", "we will",
            "follow these", "in this tutorial", "example:",
        ]
        if any(ind in text_lower for ind in tutorial_indicators):
            return "tutorial"

        # Check for reference indicators
        reference_indicators = [
            "api reference", "parameters:", "returns:", "syntax:",
            "arguments:", "options:", "methods:",
        ]
        if any(ind in text_lower for ind in reference_indicators):
            return "reference"

        # Check for overview indicators
        overview_indicators = [
            "introduction", "overview", "in this section",
            "what is", "this document", "goals:",
        ]
        if any(ind in text_lower for ind in overview_indicators):
            return "overview"

        return "unknown"
