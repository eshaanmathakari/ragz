"""S3 storage for images extracted from presentations.

This module provides a reusable S3ImageStore class for:
- Uploading images to S3
- Generating presigned URLs
- Downloading images
- Managing document images (list, delete)
"""

from __future__ import annotations

import logging

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class S3ImageStore:
    """Manage image storage in S3.

    Usage:
        store = S3ImageStore(bucket="my-bucket", prefix="images/ppt/")

        # Upload image
        s3_uri = store.upload(image_bytes, document_id="doc123", page_number=1)

        # Get presigned URL for viewing
        url = store.get_presigned_url(s3_uri)

        # Download image
        img_bytes = store.download(s3_uri)
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "images/ppt/",
        region: str | None = None,
    ):
        """Initialize S3 image store.

        Args:
            bucket: S3 bucket name.
            prefix: S3 key prefix for images.
            region: AWS region (uses default if not specified).
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.region = region
        self._client = None

    @property
    def client(self):
        """Lazy-load S3 client."""
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def upload(
        self,
        img_bytes: bytes,
        document_id: str,
        page_number: int,
        content_type: str = "image/png",
        metadata: dict | None = None,
    ) -> str:
        """Upload image to S3.

        Args:
            img_bytes: Image content.
            document_id: Document identifier.
            page_number: Page/slide number (1-indexed).
            content_type: MIME type.
            metadata: Additional metadata to store with image.

        Returns:
            S3 URI (s3://bucket/key).
        """
        s3_key = self._generate_s3_key(document_id, page_number)

        s3_metadata = {
            "document_id": document_id,
            "page_number": str(page_number),
        }
        if metadata:
            s3_metadata.update({k: str(v) for k, v in metadata.items()})

        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=img_bytes,
            ContentType=content_type,
            Metadata=s3_metadata,
        )

        s3_uri = f"s3://{self.bucket}/{s3_key}"

        logger.info(
            "Uploaded image to S3",
            s3_uri=s3_uri,
            page_number=page_number,
            size_bytes=len(img_bytes),
        )

        return s3_uri

    def upload_batch(
        self,
        images: list[tuple[str, int, bytes]],
        content_type: str = "image/png",
    ) -> list[str]:
        """Upload multiple images.

        Args:
            images: List of (document_id, page_number, img_bytes).
            content_type: MIME type.

        Returns:
            List of S3 URIs.
        """
        uris = []
        for document_id, page_number, img_bytes in images:
            uri = self.upload(img_bytes, document_id, page_number, content_type)
            uris.append(uri)
        return uris

    def get_presigned_url(self, s3_uri: str, expiration: int = 3600) -> str:
        """Generate presigned URL for image access.

        Args:
            s3_uri: S3 URI (s3://bucket/key) or just the key.
            expiration: URL expiration in seconds.

        Returns:
            Presigned URL.
        """
        bucket, key = self._parse_s3_uri(s3_uri)

        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )
        return url

    def download(self, s3_uri: str) -> bytes:
        """Download image from S3.

        Args:
            s3_uri: S3 URI (s3://bucket/key) or just the key.

        Returns:
            Image bytes.
        """
        bucket, key = self._parse_s3_uri(s3_uri)
        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def list_document_images(self, document_id: str) -> list[str]:
        """List all images for a document.

        Args:
            document_id: Document identifier.

        Returns:
            List of S3 URIs.
        """
        prefix = f"{self.prefix}{document_id}/"
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

        if "Contents" not in response:
            return []

        return [f"s3://{self.bucket}/{obj['Key']}" for obj in response["Contents"]]

    def delete_document_images(self, document_id: str) -> int:
        """Delete all images for a document.

        Args:
            document_id: Document identifier.

        Returns:
            Number of images deleted.
        """
        prefix = f"{self.prefix}{document_id}/"
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

        if "Contents" not in response:
            return 0

        objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
        if objects:
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})

        logger.info("Deleted document images", document_id=document_id, count=len(objects))
        return len(objects)

    def exists(self, s3_uri: str) -> bool:
        """Check if an image exists in S3.

        Args:
            s3_uri: S3 URI (s3://bucket/key) or just the key.

        Returns:
            True if exists, False otherwise.
        """
        bucket, key = self._parse_s3_uri(s3_uri)
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def _generate_s3_key(self, document_id: str, page_number: int) -> str:
        """Generate S3 key from document ID and page number."""
        return f"{self.prefix}{document_id}/page_{page_number:03d}.png"

    def _parse_s3_uri(self, s3_uri: str) -> tuple[str, str]:
        """Parse S3 URI into bucket and key.

        Args:
            s3_uri: S3 URI (s3://bucket/key) or just the key.

        Returns:
            Tuple of (bucket, key).
        """
        if s3_uri.startswith("s3://"):
            parts = s3_uri[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = s3_uri

        return bucket, key
