"""PPTX Image Extraction Module.

A portable, single-file module for extracting images from PowerPoint presentations.
Detects slides with SmartArt/images, renders them as PNGs, and stores in S3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import hashlib
import uuid
import subprocess
import tempfile
import os

import logging

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ImageInfo:
    """Information about an extracted image."""

    image_id: str
    document_id: str
    filename: str
    slide_number: int
    image_type: str  # "slide_render", "picture", "smartart", "chart"
    s3_uri: str = ""
    s3_key: str = ""
    width_px: int = 0
    height_px: int = 0
    size_bytes: int = 0
    extracted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SlideImageMapping:
    """Mapping of visual content found on a slide."""

    document_id: str
    filename: str
    slide_number: int
    slide_title: str = ""
    has_pictures: bool = False
    has_smartart: bool = False
    has_charts: bool = False
    images: list[ImageInfo] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of the full extraction pipeline."""

    document_id: str
    filename: str
    total_slides: int
    slides_with_images: int
    images: list[ImageInfo] = field(default_factory=list)
    mappings: list[SlideImageMapping] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# =============================================================================
# PPTXImageDetector - Detect slides with visual content
# =============================================================================


class PPTXImageDetector:
    """Detect slides containing images, SmartArt, and charts."""

    def __init__(
        self,
        include_pictures: bool = True,
        include_smartart: bool = True,
        include_charts: bool = True,
        smartart_shape_threshold: int = 5,
    ):
        """Initialize detector.

        Args:
            include_pictures: Detect embedded pictures.
            include_smartart: Detect SmartArt diagrams.
            include_charts: Detect charts.
            smartart_shape_threshold: Min shapes in group to consider as SmartArt.
        """
        self.include_pictures = include_pictures
        self.include_smartart = include_smartart
        self.include_charts = include_charts
        self.smartart_shape_threshold = smartart_shape_threshold

    def detect_image_slides(
        self, pptx_path: str | Path
    ) -> list[SlideImageMapping]:
        """Scan PPTX and return slides that contain visual content.

        Args:
            pptx_path: Path to PPTX file.

        Returns:
            List of SlideImageMapping for slides with images.
        """
        path = Path(pptx_path)
        document_id = self._generate_document_id(path)
        filename = path.name
        mappings = []

        try:
            prs = Presentation(str(path))

            for slide_num, slide in enumerate(prs.slides, 1):
                mapping = self._analyze_slide(slide, slide_num, document_id, filename)
                if mapping:
                    mappings.append(mapping)

            logger.info(
                "Detected slides with images",
                filename=filename,
                total_slides=len(prs.slides),
                slides_with_images=len(mappings),
            )

        except Exception as e:
            logger.error("Failed to detect images", filename=filename, error=str(e))
            raise

        return mappings

    def get_slide_numbers_with_images(self, pptx_path: str | Path) -> list[int]:
        """Get just the slide numbers that have visual content.

        Args:
            pptx_path: Path to PPTX file.

        Returns:
            List of slide numbers (1-indexed).
        """
        mappings = self.detect_image_slides(pptx_path)
        return [m.slide_number for m in mappings]

    def _analyze_slide(
        self, slide, slide_num: int, document_id: str, filename: str
    ) -> SlideImageMapping | None:
        """Analyze a single slide for visual content."""
        has_pictures = False
        has_smartart = False
        has_charts = False

        for shape in slide.shapes:
            if self.include_pictures and self._is_picture(shape):
                has_pictures = True
            if self.include_smartart and self._is_smartart(shape):
                has_smartart = True
            if self.include_charts and self._is_chart(shape):
                has_charts = True

        if not (has_pictures or has_smartart or has_charts):
            return None

        # Get slide title
        title = ""
        if slide.shapes.title and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text.strip()

        return SlideImageMapping(
            document_id=document_id,
            filename=filename,
            slide_number=slide_num,
            slide_title=title,
            has_pictures=has_pictures,
            has_smartart=has_smartart,
            has_charts=has_charts,
        )

    def _is_picture(self, shape) -> bool:
        """Check if shape is an embedded picture."""
        return shape.shape_type == MSO_SHAPE_TYPE.PICTURE

    def _is_smartart(self, shape) -> bool:
        """Check if shape is SmartArt.

        SmartArt typically appears as grouped shapes or as a GraphicFrame
        with diagram-related XML namespace.
        """
        # Check for grouped shapes with many children (SmartArt heuristic)
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            try:
                if hasattr(shape, "shapes"):
                    return len(shape.shapes) >= self.smartart_shape_threshold
            except Exception:
                pass

        # Check for GraphicFrame with diagram namespace
        try:
            element = shape._element
            xml_str = element.xml if hasattr(element, "xml") else str(element)
            if "dgm:" in xml_str or "diagram" in xml_str.lower():
                return True
        except Exception:
            pass

        return False

    def _is_chart(self, shape) -> bool:
        """Check if shape is a chart."""
        return shape.shape_type == MSO_SHAPE_TYPE.CHART

    def _generate_document_id(self, path: Path) -> str:
        """Generate document ID from file path and content hash."""
        try:
            content = path.read_bytes()
            hash_digest = hashlib.sha256(content).hexdigest()[:12]
            return f"{path.stem}_{hash_digest}"
        except Exception:
            return f"{path.stem}_{uuid.uuid4().hex[:12]}"


# =============================================================================
# PPTXImageExtractor - Extract/render slides as images
# =============================================================================


class PPTXImageExtractor:
    """Extract and render slides as PNG images."""

    def __init__(
        self,
        output_format: str = "png",
        use_libreoffice: bool = True,
        fallback_to_placeholder: bool = True,
    ):
        """Initialize extractor.

        Args:
            output_format: Output image format (png, jpg).
            use_libreoffice: Use LibreOffice for rendering (more accurate).
            fallback_to_placeholder: Create placeholder if rendering fails.
        """
        self.output_format = output_format
        self.use_libreoffice = use_libreoffice
        self.fallback_to_placeholder = fallback_to_placeholder
        self._libreoffice_available = None

    def extract_slides(
        self,
        pptx_path: str | Path,
        slide_numbers: list[int] | None = None,
        document_id: str | None = None,
    ) -> list[tuple[int, bytes, ImageInfo]]:
        """Render specified slides as PNG images.

        Args:
            pptx_path: Path to PPTX file.
            slide_numbers: Specific slides to extract (1-indexed). None = all.
            document_id: Optional document ID (auto-generated if not provided).

        Returns:
            List of (slide_number, png_bytes, ImageInfo).
        """
        path = Path(pptx_path)
        filename = path.name

        if document_id is None:
            document_id = self._generate_document_id(path)

        # Get total slides and validate slide numbers
        prs = Presentation(str(path))
        total_slides = len(prs.slides)

        if slide_numbers is None:
            slide_numbers = list(range(1, total_slides + 1))
        else:
            # Validate slide numbers
            slide_numbers = [n for n in slide_numbers if 1 <= n <= total_slides]

        results = []

        # Try LibreOffice rendering first
        if self.use_libreoffice and self._check_libreoffice():
            try:
                results = self._render_with_libreoffice(
                    path, slide_numbers, document_id, filename
                )
                if results:
                    return results
            except Exception as e:
                logger.warning("LibreOffice rendering failed", error=str(e))

        # Fallback: Extract embedded images or create placeholders
        for slide_num in slide_numbers:
            try:
                img_bytes, info = self._extract_slide_content(
                    prs, slide_num, document_id, filename
                )
                results.append((slide_num, img_bytes, info))
            except Exception as e:
                logger.error(
                    "Failed to extract slide",
                    slide_number=slide_num,
                    error=str(e),
                )
                if self.fallback_to_placeholder:
                    img_bytes, info = self._create_placeholder(
                        slide_num, document_id, filename
                    )
                    results.append((slide_num, img_bytes, info))

        return results

    def _check_libreoffice(self) -> bool:
        """Check if LibreOffice is available."""
        if self._libreoffice_available is not None:
            return self._libreoffice_available

        try:
            result = subprocess.run(
                ["soffice", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self._libreoffice_available = result.returncode == 0
        except Exception:
            self._libreoffice_available = False

        return self._libreoffice_available

    def _render_with_libreoffice(
        self,
        pptx_path: Path,
        slide_numbers: list[int],
        document_id: str,
        filename: str,
    ) -> list[tuple[int, bytes, ImageInfo]]:
        """Render slides using LibreOffice."""
        results = []

        with tempfile.TemporaryDirectory() as tmpdir:
            # Convert PPTX to PNG images
            subprocess.run(
                [
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "png",
                    "--outdir",
                    tmpdir,
                    str(pptx_path),
                ],
                capture_output=True,
                timeout=120,
                check=True,
            )

            # Find generated images
            for slide_num in slide_numbers:
                # LibreOffice names files like: presentation-1.png, presentation-2.png
                pattern = f"*-{slide_num}.png"
                png_files = list(Path(tmpdir).glob(pattern))

                if not png_files:
                    # Try alternate naming
                    png_files = list(Path(tmpdir).glob("*.png"))
                    if len(png_files) >= slide_num:
                        png_files = [sorted(png_files)[slide_num - 1]]

                if png_files:
                    img_bytes = png_files[0].read_bytes()
                    info = self._create_image_info(
                        img_bytes, slide_num, document_id, filename, "slide_render"
                    )
                    results.append((slide_num, img_bytes, info))

        return results

    def _extract_slide_content(
        self,
        prs: Presentation,
        slide_num: int,
        document_id: str,
        filename: str,
    ) -> tuple[bytes, ImageInfo]:
        """Extract content from a slide (embedded images or placeholder)."""
        from PIL import Image

        slide = prs.slides[slide_num - 1]
        images_found = []

        # Look for picture shapes and extract their image data
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    image = shape.image
                    img_bytes = image.blob
                    images_found.append(img_bytes)
                except Exception:
                    continue

        if images_found:
            # Return the largest image found
            largest = max(images_found, key=len)
            info = self._create_image_info(
                largest, slide_num, document_id, filename, "picture"
            )
            return largest, info

        # No embedded images found, create placeholder
        return self._create_placeholder(slide_num, document_id, filename)

    def _create_placeholder(
        self, slide_num: int, document_id: str, filename: str
    ) -> tuple[bytes, ImageInfo]:
        """Create a placeholder image for slides that couldn't be rendered."""
        from PIL import Image, ImageDraw, ImageFont

        # Create placeholder image
        width, height = 1280, 720
        img = Image.new("RGB", (width, height), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)

        # Draw slide number
        text = f"Slide {slide_num}\n(Render with LibreOffice for full content)"
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, fill=(128, 128, 128), font=font)

        # Convert to bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()

        info = self._create_image_info(
            img_bytes, slide_num, document_id, filename, "placeholder"
        )
        return img_bytes, info

    def _create_image_info(
        self,
        img_bytes: bytes,
        slide_num: int,
        document_id: str,
        filename: str,
        image_type: str,
    ) -> ImageInfo:
        """Create ImageInfo from image bytes."""
        from PIL import Image

        # Get image dimensions
        width, height = 0, 0
        try:
            img = Image.open(BytesIO(img_bytes))
            width, height = img.size
        except Exception:
            pass

        return ImageInfo(
            image_id=f"{document_id}_slide_{slide_num:03d}",
            document_id=document_id,
            filename=filename,
            slide_number=slide_num,
            image_type=image_type,
            width_px=width,
            height_px=height,
            size_bytes=len(img_bytes),
        )

    def _generate_document_id(self, path: Path) -> str:
        """Generate document ID from file path."""
        try:
            content = path.read_bytes()
            hash_digest = hashlib.sha256(content).hexdigest()[:12]
            return f"{path.stem}_{hash_digest}"
        except Exception:
            return f"{path.stem}_{uuid.uuid4().hex[:12]}"


# =============================================================================
# S3ImageStore - Upload images to S3
# =============================================================================


class S3ImageStore:
    """Manage image storage in S3."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "images/pptx/",
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
            try:
                # Try to use existing aws_config
                from rag_assist.config.aws_config import get_s3_client

                self._client = get_s3_client()
            except ImportError:
                # Fallback to direct boto3
                import boto3

                self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def upload_image(
        self,
        img_bytes: bytes,
        image_info: ImageInfo,
        content_type: str = "image/png",
    ) -> str:
        """Upload image to S3 and update ImageInfo with S3 URI.

        Args:
            img_bytes: Image content.
            image_info: Image metadata (will be updated with S3 info).
            content_type: MIME type.

        Returns:
            S3 URI (s3://bucket/key).
        """
        s3_key = self._generate_s3_key(image_info)

        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=img_bytes,
            ContentType=content_type,
            Metadata={
                "document_id": image_info.document_id,
                "slide_number": str(image_info.slide_number),
                "image_type": image_info.image_type,
            },
        )

        s3_uri = f"s3://{self.bucket}/{s3_key}"

        # Update ImageInfo
        image_info.s3_uri = s3_uri
        image_info.s3_key = s3_key

        logger.info(
            "Uploaded image to S3",
            s3_uri=s3_uri,
            slide_number=image_info.slide_number,
            size_bytes=image_info.size_bytes,
        )

        return s3_uri

    def upload_images(
        self, images: list[tuple[int, bytes, ImageInfo]]
    ) -> list[str]:
        """Upload multiple images.

        Args:
            images: List of (slide_number, img_bytes, ImageInfo).

        Returns:
            List of S3 URIs.
        """
        uris = []
        for slide_num, img_bytes, info in images:
            uri = self.upload_image(img_bytes, info)
            uris.append(uri)
        return uris

    def get_presigned_url(self, s3_uri: str, expiration: int = 3600) -> str:
        """Generate presigned URL for image access.

        Args:
            s3_uri: S3 URI (s3://bucket/key).
            expiration: URL expiration in seconds.

        Returns:
            Presigned URL.
        """
        # Parse S3 URI
        if s3_uri.startswith("s3://"):
            parts = s3_uri[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = s3_uri

        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expiration,
        )
        return url

    def download_image(self, s3_uri: str) -> bytes:
        """Download image from S3.

        Args:
            s3_uri: S3 URI (s3://bucket/key).

        Returns:
            Image bytes.
        """
        if s3_uri.startswith("s3://"):
            parts = s3_uri[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            bucket = self.bucket
            key = s3_uri

        response = self.client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def delete_document_images(self, document_id: str) -> int:
        """Delete all images for a document.

        Args:
            document_id: Document identifier.

        Returns:
            Number of images deleted.
        """
        prefix = f"{self.prefix}{document_id}/"

        # List objects
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

        if "Contents" not in response:
            return 0

        # Delete objects
        objects = [{"Key": obj["Key"]} for obj in response["Contents"]]
        if objects:
            self.client.delete_objects(
                Bucket=self.bucket, Delete={"Objects": objects}
            )

        logger.info(
            "Deleted document images",
            document_id=document_id,
            count=len(objects),
        )
        return len(objects)

    def _generate_s3_key(self, image_info: ImageInfo) -> str:
        """Generate S3 key from image metadata."""
        return (
            f"{self.prefix}{image_info.document_id}/"
            f"slide_{image_info.slide_number:03d}.png"
        )


# =============================================================================
# ImageMapper - Store/query image-to-slide mappings
# =============================================================================


class ImageMapper:
    """Create and query mappings between images and slides.

    Stores mappings in OpenSearch for integration with existing RAG system.
    """

    INDEX_MAPPING = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "image_id": {"type": "keyword"},
                "document_id": {"type": "keyword"},
                "filename": {"type": "keyword"},
                "slide_number": {"type": "integer"},
                "slide_title": {"type": "text"},
                "image_s3_uri": {"type": "keyword"},
                "image_type": {"type": "keyword"},
                "has_pictures": {"type": "boolean"},
                "has_smartart": {"type": "boolean"},
                "has_charts": {"type": "boolean"},
                "width_px": {"type": "integer"},
                "height_px": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        },
    }

    def __init__(
        self,
        opensearch_client=None,
        index_name: str = "image-mappings",
    ):
        """Initialize mapper.

        Args:
            opensearch_client: OpenSearch client (or uses default).
            index_name: Index name for mappings.
        """
        self.index_name = index_name
        self._client = opensearch_client
        self._index_created = False

    @property
    def client(self):
        """Get OpenSearch client."""
        if self._client is None:
            try:
                from rag_assist.vectorstore.opensearch_client import OpenSearchClient

                self._client = OpenSearchClient()
            except ImportError:
                raise RuntimeError(
                    "OpenSearch client not available. "
                    "Pass opensearch_client parameter or install rag_assist."
                )
        return self._client

    def ensure_index_exists(self) -> None:
        """Create index if it doesn't exist."""
        if self._index_created:
            return

        try:
            if not self.client.index_exists(self.index_name):
                self.client.create_index(self.index_name, self.INDEX_MAPPING)
                logger.info("Created image mappings index", index=self.index_name)
            self._index_created = True
        except Exception as e:
            logger.warning("Could not create index", error=str(e))

    def store_mapping(self, mapping: SlideImageMapping) -> None:
        """Store image-to-slide mapping.

        Args:
            mapping: Slide mapping with images.
        """
        self.ensure_index_exists()

        for image in mapping.images:
            doc = {
                "image_id": image.image_id,
                "document_id": mapping.document_id,
                "filename": mapping.filename,
                "slide_number": mapping.slide_number,
                "slide_title": mapping.slide_title,
                "image_s3_uri": image.s3_uri,
                "image_type": image.image_type,
                "has_pictures": mapping.has_pictures,
                "has_smartart": mapping.has_smartart,
                "has_charts": mapping.has_charts,
                "width_px": image.width_px,
                "height_px": image.height_px,
                "created_at": datetime.utcnow().isoformat(),
            }

            self.client.index_document(
                index_name=self.index_name,
                document_id=image.image_id,
                document=doc,
            )

        logger.info(
            "Stored image mapping",
            document_id=mapping.document_id,
            slide_number=mapping.slide_number,
            image_count=len(mapping.images),
        )

    def store_mappings(self, mappings: list[SlideImageMapping]) -> int:
        """Store multiple mappings.

        Args:
            mappings: List of slide mappings.

        Returns:
            Number of mappings stored.
        """
        count = 0
        for mapping in mappings:
            if mapping.images:
                self.store_mapping(mapping)
                count += len(mapping.images)
        return count

    def get_images_for_slide(
        self, document_id: str, slide_number: int
    ) -> list[dict[str, Any]]:
        """Get images for a specific slide.

        Args:
            document_id: Document identifier.
            slide_number: Slide number (1-indexed).

        Returns:
            List of image records.
        """
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"slide_number": slide_number}},
                    ]
                }
            }
        }

        try:
            response = self.client.search(index_name=self.index_name, query=query)
            return [hit["_source"] for hit in response.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error("Failed to query images", error=str(e))
            return []

    def get_images_for_document(self, document_id: str) -> list[dict[str, Any]]:
        """Get all images for a document.

        Args:
            document_id: Document identifier.

        Returns:
            List of image records.
        """
        query = {
            "query": {"term": {"document_id": document_id}},
            "size": 1000,
            "sort": [{"slide_number": "asc"}],
        }

        try:
            response = self.client.search(index_name=self.index_name, query=query)
            return [hit["_source"] for hit in response.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error("Failed to query images", error=str(e))
            return []

    def get_s3_uris_for_slide(
        self, document_id: str, slide_number: int
    ) -> list[str]:
        """Get S3 URIs for a slide.

        Args:
            document_id: Document identifier.
            slide_number: Slide number.

        Returns:
            List of S3 URIs.
        """
        images = self.get_images_for_slide(document_id, slide_number)
        return [img["image_s3_uri"] for img in images if img.get("image_s3_uri")]

    def delete_document_mappings(self, document_id: str) -> int:
        """Delete all mappings for a document.

        Args:
            document_id: Document identifier.

        Returns:
            Number of mappings deleted.
        """
        query = {"query": {"term": {"document_id": document_id}}}

        try:
            response = self.client.delete_by_query(
                index_name=self.index_name, query=query
            )
            deleted = response.get("deleted", 0)
            logger.info(
                "Deleted document mappings",
                document_id=document_id,
                count=deleted,
            )
            return deleted
        except Exception as e:
            logger.error("Failed to delete mappings", error=str(e))
            return 0


# =============================================================================
# Pipeline Function
# =============================================================================


def extract_images_from_pptx(
    pptx_path: str | Path,
    s3_bucket: str,
    s3_prefix: str = "images/pptx/",
    opensearch_client=None,
    store_mappings: bool = True,
    slide_numbers: list[int] | None = None,
) -> ExtractionResult:
    """Full pipeline: detect, extract, upload, and map images from PPTX.

    Args:
        pptx_path: Path to PPTX file.
        s3_bucket: S3 bucket for image storage.
        s3_prefix: S3 key prefix.
        opensearch_client: Optional OpenSearch client for mappings.
        store_mappings: Whether to store mappings in OpenSearch.
        slide_numbers: Specific slides to process (None = auto-detect).

    Returns:
        ExtractionResult with all extracted images and mappings.
    """
    path = Path(pptx_path)
    filename = path.name
    errors = []

    logger.info("Starting image extraction", filename=filename)

    # Step 1: Detect slides with images
    detector = PPTXImageDetector()
    mappings = detector.detect_image_slides(path)

    if slide_numbers:
        # Filter to requested slides
        mappings = [m for m in mappings if m.slide_number in slide_numbers]

    if not mappings:
        logger.info("No slides with images found", filename=filename)
        prs = Presentation(str(path))
        return ExtractionResult(
            document_id=detector._generate_document_id(path),
            filename=filename,
            total_slides=len(prs.slides),
            slides_with_images=0,
        )

    document_id = mappings[0].document_id

    # Step 2: Extract/render images
    extractor = PPTXImageExtractor()
    detected_slides = [m.slide_number for m in mappings]
    extracted = extractor.extract_slides(path, detected_slides, document_id)

    # Step 3: Upload to S3
    store = S3ImageStore(s3_bucket, s3_prefix)
    try:
        store.upload_images(extracted)
    except Exception as e:
        errors.append(f"S3 upload error: {str(e)}")
        logger.error("Failed to upload images", error=str(e))

    # Update mappings with extracted images
    slide_to_info = {slide_num: info for slide_num, _, info in extracted}
    for mapping in mappings:
        if mapping.slide_number in slide_to_info:
            mapping.images = [slide_to_info[mapping.slide_number]]

    # Step 4: Store mappings in OpenSearch
    if store_mappings and opensearch_client is not None:
        try:
            mapper = ImageMapper(opensearch_client)
            mapper.store_mappings(mappings)
        except Exception as e:
            errors.append(f"Mapping storage error: {str(e)}")
            logger.error("Failed to store mappings", error=str(e))

    # Build result
    all_images = [info for _, _, info in extracted]
    prs = Presentation(str(path))

    result = ExtractionResult(
        document_id=document_id,
        filename=filename,
        total_slides=len(prs.slides),
        slides_with_images=len(mappings),
        images=all_images,
        mappings=mappings,
        errors=errors,
    )

    logger.info(
        "Image extraction complete",
        filename=filename,
        slides_extracted=len(all_images),
        errors=len(errors),
    )

    return result
