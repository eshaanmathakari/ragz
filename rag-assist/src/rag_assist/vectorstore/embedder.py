"""Amazon Titan Embeddings wrapper for text embedding generation."""

import json
from functools import lru_cache
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_assist.config import get_bedrock_runtime_client
from rag_assist.config.settings import get_settings

logger = structlog.get_logger(__name__)


class TitanEmbedder:
    """Amazon Titan Text Embeddings V2 wrapper.

    Generates 1024-dimensional embeddings for text using Amazon Bedrock.
    """

    def __init__(
        self,
        model_id: str | None = None,
        dimension: int = 1024,
        normalize: bool = True,
    ):
        """Initialize Titan embedder.

        Args:
            model_id: Bedrock model ID for embeddings.
            dimension: Embedding dimension (256, 384, or 1024).
            normalize: Whether to normalize embeddings.
        """
        settings = get_settings()
        self.model_id = model_id or settings.bedrock.embedding_model_id
        self.dimension = dimension
        self.normalize = normalize
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-load Bedrock runtime client."""
        if self._client is None:
            self._client = get_bedrock_runtime_client()
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (1024 dimensions).
        """
        if not text or not text.strip():
            return [0.0] * self.dimension

        # Truncate text if too long (Titan has 8k token limit)
        max_chars = 25000  # Approximate safe limit
        if len(text) > max_chars:
            text = text[:max_chars]
            logger.warning(f"Text truncated to {max_chars} chars for embedding")

        # Prepare request body
        body = {
            "inputText": text,
            "dimensions": self.dimension,
            "normalize": self.normalize,
        }

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )

            response_body = json.loads(response["body"].read())
            embedding = response_body.get("embedding", [])

            if len(embedding) != self.dimension:
                logger.warning(
                    f"Unexpected embedding dimension: {len(embedding)}, expected {self.dimension}"
                )

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 10,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Note: Titan doesn't support batch embedding, so we process sequentially.

        Args:
            texts: List of texts to embed.
            batch_size: Not used (for API compatibility).

        Returns:
            List of embedding vectors.
        """
        logger.info(f"Generating embeddings for {len(texts)} texts")

        embeddings = []
        for i, text in enumerate(texts):
            try:
                embedding = self.embed(text)
                embeddings.append(embedding)

                if (i + 1) % 100 == 0:
                    logger.info(f"Embedded {i + 1}/{len(texts)} texts")

            except Exception as e:
                logger.error(f"Failed to embed text {i}: {str(e)}")
                # Return zero vector on failure
                embeddings.append([0.0] * self.dimension)

        logger.info(f"Embedding generation complete: {len(embeddings)} vectors")
        return embeddings

    async def embed_async(self, text: str) -> list[float]:
        """Async embedding generation (runs in thread pool).

        Args:
            text: Text to embed.

        Returns:
            Embedding vector.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def embed_batch_async(
        self,
        texts: list[str],
        max_concurrent: int = 5,
    ) -> list[list[float]]:
        """Async batch embedding with concurrency control.

        Args:
            texts: List of texts to embed.
            max_concurrent: Maximum concurrent requests.

        Returns:
            List of embedding vectors.
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_with_semaphore(text: str) -> list[float]:
            async with semaphore:
                return await self.embed_async(text)

        tasks = [embed_with_semaphore(text) for text in texts]
        return await asyncio.gather(*tasks)


@lru_cache(maxsize=1)
def get_embedder() -> TitanEmbedder:
    """Get cached Titan embedder instance.

    Returns:
        TitanEmbedder instance.
    """
    return TitanEmbedder()
