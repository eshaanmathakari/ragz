"""Keyword extraction using YAKE algorithm."""

import structlog
import yake

logger = structlog.get_logger(__name__)


class KeywordExtractor:
    """Extract keywords from text using YAKE algorithm.

    YAKE (Yet Another Keyword Extractor) is an unsupervised automatic
    keyword extraction method that doesn't require training data.
    """

    def __init__(
        self,
        language: str = "en",
        max_ngram_size: int = 3,
        deduplication_threshold: float = 0.9,
        num_keywords: int = 10,
    ):
        """Initialize keyword extractor.

        Args:
            language: Language code for text analysis.
            max_ngram_size: Maximum n-gram size for keywords.
            deduplication_threshold: Threshold for removing similar keywords.
            num_keywords: Maximum number of keywords to extract.
        """
        self.language = language
        self.max_ngram_size = max_ngram_size
        self.deduplication_threshold = deduplication_threshold
        self.num_keywords = num_keywords

        self._extractor = yake.KeywordExtractor(
            lan=language,
            n=max_ngram_size,
            dedupLim=deduplication_threshold,
            top=num_keywords,
            features=None,
        )

    def extract(self, text: str, top_k: int | None = None) -> list[str]:
        """Extract keywords from text.

        Args:
            text: Text to extract keywords from.
            top_k: Number of keywords to return (overrides default).

        Returns:
            List of extracted keywords.
        """
        if not text or not text.strip():
            return []

        try:
            # YAKE returns list of (keyword, score) tuples
            # Lower score = more important
            keywords = self._extractor.extract_keywords(text)

            # Get top_k keywords
            top_k = top_k or self.num_keywords
            top_keywords = keywords[:top_k]

            # Return just the keyword strings
            return [kw[0] for kw in top_keywords]

        except Exception as e:
            logger.warning(f"Keyword extraction failed: {str(e)}")
            return []

    def extract_with_scores(self, text: str, top_k: int | None = None) -> list[tuple[str, float]]:
        """Extract keywords with their importance scores.

        Args:
            text: Text to extract keywords from.
            top_k: Number of keywords to return.

        Returns:
            List of (keyword, score) tuples. Lower scores = more important.
        """
        if not text or not text.strip():
            return []

        try:
            keywords = self._extractor.extract_keywords(text)
            top_k = top_k or self.num_keywords
            return keywords[:top_k]

        except Exception as e:
            logger.warning(f"Keyword extraction failed: {str(e)}")
            return []

    def extract_batch(self, texts: list[str], top_k: int | None = None) -> list[list[str]]:
        """Extract keywords from multiple texts.

        Args:
            texts: List of texts to process.
            top_k: Number of keywords per text.

        Returns:
            List of keyword lists.
        """
        return [self.extract(text, top_k) for text in texts]
