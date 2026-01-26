"""OpenSearch Serverless client for vector storage and search."""

from functools import lru_cache
from typing import Any

import structlog
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection
from tenacity import retry, stop_after_attempt, wait_exponential

from rag_assist.config.opensearch_config import (
    INDEX_NAME,
    SEARCH_PIPELINE_NAME,
    get_index_mapping,
    get_search_pipeline_config,
)
from rag_assist.config.settings import get_settings

logger = structlog.get_logger(__name__)


class OpenSearchClient:
    """Client for Amazon OpenSearch Serverless.

    Handles connection, index management, and basic operations.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        index_name: str | None = None,
        use_ssl: bool = True,
    ):
        """Initialize OpenSearch client.

        Args:
            endpoint: OpenSearch endpoint URL.
            index_name: Index name for operations.
            use_ssl: Use SSL for connection.
        """
        settings = get_settings()

        self.endpoint = endpoint or settings.opensearch.endpoint
        self.index_name = index_name or settings.opensearch.index_name
        self.use_ssl = use_ssl

        self._client: OpenSearch | None = None

    @property
    def client(self) -> OpenSearch:
        """Lazy-load OpenSearch client with AWS authentication."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> OpenSearch:
        """Create authenticated OpenSearch client.

        Returns:
            OpenSearch client instance.
        """
        import boto3

        settings = get_settings()

        # Get AWS credentials for signing
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, settings.aws.region, "aoss")

        # Parse endpoint
        host = self.endpoint.replace("https://", "").replace("http://", "")

        client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=auth,
            use_ssl=self.use_ssl,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30,
        )

        logger.info(f"OpenSearch client created for endpoint: {self.endpoint}")
        return client

    def index_exists(self) -> bool:
        """Check if the index exists.

        Returns:
            True if index exists.
        """
        try:
            return self.client.indices.exists(index=self.index_name)
        except Exception as e:
            logger.error(f"Error checking index existence: {str(e)}")
            return False

    def create_index(self, force: bool = False) -> bool:
        """Create the index with configured mapping.

        Args:
            force: Delete existing index if present.

        Returns:
            True if index was created successfully.
        """
        try:
            if self.index_exists():
                if force:
                    logger.warning(f"Deleting existing index: {self.index_name}")
                    self.client.indices.delete(index=self.index_name)
                else:
                    logger.info(f"Index already exists: {self.index_name}")
                    return True

            # Create index with mapping
            mapping = get_index_mapping()
            self.client.indices.create(index=self.index_name, body=mapping)

            logger.info(f"Index created: {self.index_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create index: {str(e)}")
            return False

    def create_search_pipeline(self) -> bool:
        """Create hybrid search normalization pipeline.

        Returns:
            True if pipeline was created successfully.
        """
        try:
            pipeline_config = get_search_pipeline_config()

            self.client.transport.perform_request(
                method="PUT",
                url=f"/_search/pipeline/{SEARCH_PIPELINE_NAME}",
                body=pipeline_config,
            )

            logger.info(f"Search pipeline created: {SEARCH_PIPELINE_NAME}")
            return True

        except Exception as e:
            logger.error(f"Failed to create search pipeline: {str(e)}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def index_document(
        self,
        doc_id: str,
        document: dict[str, Any],
    ) -> bool:
        """Index a single document.

        Args:
            doc_id: Document ID.
            document: Document body.

        Returns:
            True if indexing succeeded.
        """
        try:
            self.client.index(
                index=self.index_name,
                id=doc_id,
                body=document,
                refresh=False,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to index document {doc_id}: {str(e)}")
            raise

    def bulk_index(
        self,
        documents: list[tuple[str, dict[str, Any]]],
        chunk_size: int = 100,
    ) -> tuple[int, int]:
        """Bulk index multiple documents.

        Args:
            documents: List of (doc_id, document) tuples.
            chunk_size: Number of documents per bulk request.

        Returns:
            Tuple of (successful_count, failed_count).
        """
        from opensearchpy.helpers import bulk

        successful = 0
        failed = 0

        # Prepare bulk actions
        actions = []
        for doc_id, document in documents:
            action = {
                "_index": self.index_name,
                "_id": doc_id,
                "_source": document,
            }
            actions.append(action)

        # Process in chunks
        for i in range(0, len(actions), chunk_size):
            chunk = actions[i : i + chunk_size]
            try:
                success, errors = bulk(
                    self.client,
                    chunk,
                    raise_on_error=False,
                    refresh=False,
                )
                successful += success
                failed += len(errors) if errors else 0

                if errors:
                    for error in errors[:5]:  # Log first 5 errors
                        logger.warning(f"Bulk index error: {error}")

            except Exception as e:
                logger.error(f"Bulk index failed: {str(e)}")
                failed += len(chunk)

        # Refresh index after bulk insert
        try:
            self.client.indices.refresh(index=self.index_name)
        except Exception:
            pass

        logger.info(f"Bulk index complete: {successful} successful, {failed} failed")
        return successful, failed

    def search(
        self,
        query: dict[str, Any],
        size: int = 10,
        use_pipeline: bool = True,
    ) -> dict[str, Any]:
        """Execute a search query.

        Args:
            query: OpenSearch query body.
            size: Number of results to return.
            use_pipeline: Use the hybrid search pipeline.

        Returns:
            Search response.
        """
        params = {}
        if use_pipeline:
            params["search_pipeline"] = SEARCH_PIPELINE_NAME

        try:
            response = self.client.search(
                index=self.index_name,
                body=query,
                size=size,
                params=params,
            )
            return response
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Get a document by ID.

        Args:
            doc_id: Document ID.

        Returns:
            Document source or None if not found.
        """
        try:
            response = self.client.get(index=self.index_name, id=doc_id)
            return response.get("_source")
        except Exception:
            return None

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document by ID.

        Args:
            doc_id: Document ID.

        Returns:
            True if deletion succeeded.
        """
        try:
            self.client.delete(index=self.index_name, id=doc_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {str(e)}")
            return False

    def get_document_count(self) -> int:
        """Get total document count in index.

        Returns:
            Number of documents.
        """
        try:
            response = self.client.count(index=self.index_name)
            return response.get("count", 0)
        except Exception:
            return 0

    def get_existing_hashes(self) -> set[str]:
        """Get all content hashes in the index.

        Returns:
            Set of content hash strings.
        """
        hashes = set()

        try:
            # Use scroll API for large result sets
            query = {
                "_source": ["content_hash"],
                "query": {"match_all": {}},
            }

            response = self.client.search(
                index=self.index_name,
                body=query,
                scroll="2m",
                size=1000,
            )

            scroll_id = response.get("_scroll_id")

            while True:
                hits = response.get("hits", {}).get("hits", [])
                if not hits:
                    break

                for hit in hits:
                    content_hash = hit.get("_source", {}).get("content_hash")
                    if content_hash:
                        hashes.add(content_hash)

                response = self.client.scroll(scroll_id=scroll_id, scroll="2m")

            # Clear scroll
            self.client.clear_scroll(scroll_id=scroll_id)

        except Exception as e:
            logger.error(f"Failed to get existing hashes: {str(e)}")

        return hashes

    def health_check(self) -> dict[str, Any]:
        """Check cluster health.

        Returns:
            Health status dict.
        """
        try:
            health = self.client.cluster.health()
            return {
                "status": health.get("status"),
                "cluster_name": health.get("cluster_name"),
                "number_of_nodes": health.get("number_of_nodes"),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


@lru_cache(maxsize=1)
def get_opensearch_client() -> OpenSearchClient:
    """Get cached OpenSearch client instance.

    Returns:
        OpenSearchClient instance.
    """
    return OpenSearchClient()
