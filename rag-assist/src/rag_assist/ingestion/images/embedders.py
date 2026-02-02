"""Embedding models for text and images via Amazon Bedrock.

This module provides:
- CohereTextEmbedder: Text embeddings using Cohere via Bedrock
- TitanMultimodalEmbedder: Image embeddings using Titan Multimodal via Bedrock

Both embedders are designed to be configurable and work with the
existing aws_config module when available.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class CohereTextEmbedder:
    """Generate text embeddings using Cohere via Amazon Bedrock.

    Usage:
        embedder = CohereTextEmbedder()

        # Single text
        embedding = embedder.embed("Hello world")

        # Batch (more efficient)
        embeddings = embedder.embed_batch(["Hello", "World"])

        # For queries (different input_type)
        query_embedding = embedder.embed("search query", input_type="search_query")
    """

    # Default model ID - edit based on your Bedrock configuration
    DEFAULT_MODEL_ID = "cohere.embed-english-v3"

    def __init__(
        self,
        model_id: str | None = None,
        dimension: int = 1024,
        region: str | None = None,
    ):
        """Initialize Cohere text embedder.

        Args:
            model_id: Bedrock model ID. Uses DEFAULT_MODEL_ID if not specified.
            dimension: Embedding dimension. Cohere v3 supports 1024.
            region: AWS region for Bedrock. Uses default if not specified.
        """
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.dimension = dimension
        self.region = region
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load Bedrock runtime client."""
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "bedrock-runtime", region_name=self.region
            )
        return self._client

    def embed(self, text: str, input_type: str = "search_document") -> list[float]:
        """Embed single text.

        Args:
            text: Text to embed.
            input_type: Type of input for Cohere model.
                       "search_document" for indexing (default).
                       "search_query" for queries.

        Returns:
            Embedding vector as list of floats.
        """
        embeddings = self.embed_batch([text], input_type=input_type)
        return embeddings[0] if embeddings else []

    def embed_batch(
        self, texts: list[str], input_type: str = "search_document"
    ) -> list[list[float]]:
        """Embed batch of texts.

        Args:
            texts: List of texts to embed.
            input_type: Type of input for Cohere model.
                       "search_document" for indexing (default).
                       "search_query" for queries.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        # Filter empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        try:
            body = json.dumps({
                "texts": valid_texts,
                "input_type": input_type,
                "truncate": "END",  # Truncate if text exceeds max length
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
            )

            response_body = json.loads(response["body"].read())
            embeddings = response_body.get("embeddings", [])

            logger.debug(
                "Generated text embeddings",
                count=len(embeddings),
                model=self.model_id,
            )

            # Map back to original texts (empty texts get empty embeddings)
            result = []
            emb_idx = 0
            for text in texts:
                if text and text.strip():
                    result.append(embeddings[emb_idx] if emb_idx < len(embeddings) else [])
                    emb_idx += 1
                else:
                    result.append([])

            return result

        except Exception as e:
            logger.error(f"Failed to generate text embeddings: {e}")
            return [[] for _ in texts]


class TitanMultimodalEmbedder:
    """Generate image embeddings using Titan Multimodal via Amazon Bedrock.

    Usage:
        embedder = TitanMultimodalEmbedder()

        # Single image
        with open("image.png", "rb") as f:
            embedding = embedder.embed_image(f.read())

        # Batch (sequential, Titan doesn't support true batching)
        embeddings = embedder.embed_image_batch([img_bytes1, img_bytes2])
    """

    # Default model ID - edit based on your Bedrock configuration
    DEFAULT_MODEL_ID = "amazon.titan-embed-image-v1"

    def __init__(
        self,
        model_id: str | None = None,
        dimension: int = 1024,
        region: str | None = None,
    ):
        """Initialize Titan multimodal embedder.

        Args:
            model_id: Bedrock model ID. Uses DEFAULT_MODEL_ID if not specified.
            dimension: Embedding dimension. Titan supports 256, 384, 1024.
            region: AWS region for Bedrock. Uses default if not specified.
        """
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.dimension = dimension
        self.region = region
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load Bedrock runtime client."""
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "bedrock-runtime", region_name=self.region
            )
        return self._client

    def embed_image(self, image_bytes: bytes) -> list[float]:
        """Embed single image.

        Args:
            image_bytes: Image content as bytes (PNG, JPEG, etc.).

        Returns:
            Embedding vector as list of floats.
        """
        if not image_bytes:
            return []

        try:
            # Encode image as base64
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            body = json.dumps({
                "inputImage": image_b64,
                "embeddingConfig": {
                    "outputEmbeddingLength": self.dimension,
                },
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
            )

            response_body = json.loads(response["body"].read())
            embedding = response_body.get("embedding", [])

            logger.debug(
                "Generated image embedding",
                dimension=len(embedding),
                model=self.model_id,
            )

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate image embedding: {e}")
            return []

    def embed_image_batch(self, images: list[bytes]) -> list[list[float]]:
        """Embed batch of images.

        Note: Titan Multimodal doesn't support true batching,
        so this processes images sequentially.

        Args:
            images: List of image bytes.

        Returns:
            List of embedding vectors.
        """
        embeddings = []
        for i, img_bytes in enumerate(images):
            embedding = self.embed_image(img_bytes)
            embeddings.append(embedding)

            if (i + 1) % 10 == 0:
                logger.info(f"Embedded {i + 1}/{len(images)} images")

        return embeddings

    def embed_text(self, text: str) -> list[float]:
        """Embed text using Titan Multimodal (for text-image similarity).

        Note: Titan Multimodal can also embed text for cross-modal search.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.
        """
        if not text or not text.strip():
            return []

        try:
            body = json.dumps({
                "inputText": text,
                "embeddingConfig": {
                    "outputEmbeddingLength": self.dimension,
                },
            })

            response = self.client.invoke_model(
                modelId=self.model_id,
                body=body,
            )

            response_body = json.loads(response["body"].read())
            embedding = response_body.get("embedding", [])

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate text embedding via Titan: {e}")
            return []


# Convenience factory functions


def get_text_embedder(
    model_id: str | None = None,
    dimension: int = 1024,
) -> CohereTextEmbedder:
    """Get a text embedder instance.

    Args:
        model_id: Optional custom model ID.
        dimension: Embedding dimension.

    Returns:
        CohereTextEmbedder instance.
    """
    return CohereTextEmbedder(model_id=model_id, dimension=dimension)


def get_image_embedder(
    model_id: str | None = None,
    dimension: int = 1024,
) -> TitanMultimodalEmbedder:
    """Get an image embedder instance.

    Args:
        model_id: Optional custom model ID.
        dimension: Embedding dimension.

    Returns:
        TitanMultimodalEmbedder instance.
    """
    return TitanMultimodalEmbedder(model_id=model_id, dimension=dimension)
