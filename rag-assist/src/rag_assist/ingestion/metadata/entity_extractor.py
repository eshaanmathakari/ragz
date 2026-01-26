"""Named entity extraction using spaCy."""

from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)

# Entity types we care about for learning content
RELEVANT_ENTITY_TYPES = {
    "PERSON",       # People names
    "ORG",          # Organizations
    "GPE",          # Geopolitical entities (countries, cities)
    "PRODUCT",      # Products
    "EVENT",        # Events
    "WORK_OF_ART",  # Titles of books, songs, etc.
    "LAW",          # Laws, regulations
    "DATE",         # Dates
    "MONEY",        # Monetary values
    "PERCENT",      # Percentages
    "QUANTITY",     # Quantities
}


@lru_cache(maxsize=1)
def get_spacy_model():
    """Load spaCy model lazily (cached).

    Returns:
        Loaded spaCy model.
    """
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except OSError:
        logger.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
        return None


class EntityExtractor:
    """Extract named entities from text using spaCy.

    Extracts entities like people, organizations, locations, dates, etc.
    """

    def __init__(
        self,
        entity_types: set[str] | None = None,
        min_entity_length: int = 2,
    ):
        """Initialize entity extractor.

        Args:
            entity_types: Set of entity types to extract (default: RELEVANT_ENTITY_TYPES).
            min_entity_length: Minimum entity text length.
        """
        self.entity_types = entity_types or RELEVANT_ENTITY_TYPES
        self.min_entity_length = min_entity_length
        self._nlp = None

    @property
    def nlp(self):
        """Lazy-load spaCy model."""
        if self._nlp is None:
            self._nlp = get_spacy_model()
        return self._nlp

    def extract(self, text: str, max_entities: int = 20) -> list[dict[str, str]]:
        """Extract named entities from text.

        Args:
            text: Text to extract entities from.
            max_entities: Maximum number of entities to return.

        Returns:
            List of entity dictionaries with 'text' and 'type' keys.
        """
        if not text or not text.strip():
            return []

        if not self.nlp:
            return []

        try:
            # Process text with spaCy
            doc = self.nlp(text[:100000])  # Limit text length for performance

            entities = []
            seen = set()  # Deduplicate entities

            for ent in doc.ents:
                # Filter by entity type
                if ent.label_ not in self.entity_types:
                    continue

                # Filter by length
                entity_text = ent.text.strip()
                if len(entity_text) < self.min_entity_length:
                    continue

                # Deduplicate
                key = (entity_text.lower(), ent.label_)
                if key in seen:
                    continue
                seen.add(key)

                entities.append({
                    "text": entity_text,
                    "type": ent.label_,
                })

                if len(entities) >= max_entities:
                    break

            return entities

        except Exception as e:
            logger.warning(f"Entity extraction failed: {str(e)}")
            return []

    def extract_by_type(self, text: str) -> dict[str, list[str]]:
        """Extract entities grouped by type.

        Args:
            text: Text to extract entities from.

        Returns:
            Dictionary mapping entity types to lists of entity texts.
        """
        entities = self.extract(text)

        grouped: dict[str, list[str]] = {}
        for entity in entities:
            entity_type = entity["type"]
            if entity_type not in grouped:
                grouped[entity_type] = []
            grouped[entity_type].append(entity["text"])

        return grouped

    def extract_batch(self, texts: list[str], max_entities: int = 20) -> list[list[dict[str, str]]]:
        """Extract entities from multiple texts.

        Args:
            texts: List of texts to process.
            max_entities: Maximum entities per text.

        Returns:
            List of entity lists.
        """
        return [self.extract(text, max_entities) for text in texts]
