"""Data models for PPT content extraction.

This module defines the data classes used throughout the 2-step extraction framework:
- Step 1 (PPT Path): SlideTextContent for text from PPTX
- Step 2 (PDF Path): PDFPageContent for text + images from PDF

All content is linked by document_id + slide_number/page_number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# =============================================================================
# Step 1: PPT Text Content
# =============================================================================


@dataclass
class SlideTextContent:
    """Text content extracted from a PPTX slide.

    This is the PRIMARY text source for RAG retrieval.
    """

    document_id: str
    filename: str
    slide_number: int  # 1-indexed
    title: str
    body_text: str  # All text concatenated
    speaker_notes: str = ""
    tables: list[str] = field(default_factory=list)  # Tables as text
    has_visual_content: bool = False  # Flag if slide has images/charts

    @property
    def full_text(self) -> str:
        """Get all text content concatenated."""
        parts = []
        if self.title:
            parts.append(self.title)
        if self.body_text:
            parts.append(self.body_text)
        if self.speaker_notes:
            parts.append(f"Notes: {self.speaker_notes}")
        if self.tables:
            for i, table in enumerate(self.tables, 1):
                parts.append(f"Table {i}: {table}")
        return "\n\n".join(parts)

    @property
    def content_id(self) -> str:
        """Unique content identifier."""
        return f"{self.document_id}_ppt_slide_{self.slide_number:03d}"


# =============================================================================
# Step 2: PDF Content (Text + Images)
# =============================================================================


@dataclass
class PDFPageContent:
    """Combined text and image from a PDF page.

    page_number corresponds to slide_number for linking.
    """

    document_id: str
    filename: str
    page_number: int  # 1-indexed, = slide_number
    text_content: str  # Extracted text
    image_bytes: bytes = b""  # PNG render of page
    width_px: int = 0
    height_px: int = 0
    s3_uri: str = ""  # After upload

    @property
    def has_image(self) -> bool:
        """Check if image data is available."""
        return len(self.image_bytes) > 0

    @property
    def size_bytes(self) -> int:
        """Image size in bytes."""
        return len(self.image_bytes)

    @property
    def content_id(self) -> str:
        """Unique content identifier."""
        return f"{self.document_id}_pdf_page_{self.page_number:03d}"


@dataclass
class PageTextContent:
    """Text only from a PDF page (when image extraction not needed/failed)."""

    document_id: str
    filename: str
    page_number: int  # 1-indexed
    text_content: str

    @property
    def content_id(self) -> str:
        """Unique content identifier."""
        return f"{self.document_id}_pdf_text_{self.page_number:03d}"


@dataclass
class PageImageContent:
    """Image only from a PDF page."""

    document_id: str
    filename: str
    page_number: int  # 1-indexed
    image_bytes: bytes
    width_px: int
    height_px: int
    s3_uri: str = ""

    @property
    def has_image(self) -> bool:
        """Check if image data is available."""
        return len(self.image_bytes) > 0

    @property
    def size_bytes(self) -> int:
        """Image size in bytes."""
        return len(self.image_bytes)

    @property
    def content_id(self) -> str:
        """Unique content identifier."""
        return f"{self.document_id}_pdf_img_{self.page_number:03d}"


# =============================================================================
# Extraction Results
# =============================================================================


@dataclass
class PPTExtractionResult:
    """Result from Step 1: PPT text extraction."""

    document_id: str
    filename: str
    total_slides: int
    slides: list[SlideTextContent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def slide_count(self) -> int:
        """Number of slides with content."""
        return len(self.slides)

    @property
    def slides_with_visuals(self) -> list[int]:
        """Slide numbers that have visual content."""
        return [s.slide_number for s in self.slides if s.has_visual_content]


@dataclass
class PDFExtractionResult:
    """Result from Step 2: PDF content extraction."""

    document_id: str
    filename: str
    total_pages: int
    pages: list[PDFPageContent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def page_count(self) -> int:
        """Number of pages extracted."""
        return len(self.pages)

    @property
    def pages_with_images(self) -> int:
        """Number of pages with image data."""
        return sum(1 for p in self.pages if p.has_image)


# =============================================================================
# Indexing Models
# =============================================================================


@dataclass
class IndexedTextDocument:
    """Text document indexed in OpenSearch."""

    content_id: str
    document_id: str
    filename: str
    slide_number: int
    content_type: str = "text"  # "text" or "ppt_text" or "pdf_text"
    source: str = "ppt"  # "ppt" or "pdf"

    # Content
    text_content: str = ""
    title: str = ""

    # Embedding (populated after embedding)
    text_embedding: list[float] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_opensearch_doc(self) -> dict[str, Any]:
        """Convert to OpenSearch document format."""
        return {
            "content_id": self.content_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "slide_number": self.slide_number,
            "content_type": self.content_type,
            "source": self.source,
            "text_content": self.text_content,
            "title": self.title,
            "text_embedding": self.text_embedding,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class IndexedImageDocument:
    """Image document indexed in OpenSearch."""

    content_id: str
    document_id: str
    filename: str
    slide_number: int  # = page_number
    content_type: str = "image"

    # Image info
    image_s3_uri: str = ""
    width_px: int = 0
    height_px: int = 0

    # Embedding (populated after embedding)
    image_embedding: list[float] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_opensearch_doc(self) -> dict[str, Any]:
        """Convert to OpenSearch document format."""
        return {
            "content_id": self.content_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "slide_number": self.slide_number,
            "content_type": self.content_type,
            "image_s3_uri": self.image_s3_uri,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "image_embedding": self.image_embedding,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Retrieval Models
# =============================================================================


@dataclass
class RetrievalResult:
    """Result from content retrieval."""

    document_id: str
    slide_number: int
    filename: str = ""

    # Text content
    text_content: str = ""
    title: str = ""
    text_score: float = 0.0

    # Linked image (if available)
    image_s3_uri: str | None = None
    image_presigned_url: str | None = None
    image_score: float | None = None

    # Source info
    text_source: str = "ppt"  # "ppt" or "pdf"

    @property
    def has_image(self) -> bool:
        """Check if image is available."""
        return self.image_s3_uri is not None


@dataclass
class SlideContent:
    """Complete content for a single slide (text + image)."""

    document_id: str
    slide_number: int
    filename: str = ""

    # Text content (from PPT)
    ppt_text: SlideTextContent | None = None

    # PDF content (text + image)
    pdf_text: str | None = None
    pdf_image_s3_uri: str | None = None
    pdf_image_presigned_url: str | None = None

    @property
    def primary_text(self) -> str:
        """Get primary text (PPT preferred, fallback to PDF)."""
        if self.ppt_text:
            return self.ppt_text.full_text
        return self.pdf_text or ""

    @property
    def has_image(self) -> bool:
        """Check if image is available."""
        return self.pdf_image_s3_uri is not None


# =============================================================================
# Indexing Results
# =============================================================================


@dataclass
class IndexingResult:
    """Result from indexing operation."""

    document_id: str
    filename: str
    text_documents_indexed: int = 0
    image_documents_indexed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_indexed(self) -> int:
        """Total documents indexed."""
        return self.text_documents_indexed + self.image_documents_indexed

    @property
    def success(self) -> bool:
        """Check if indexing was successful."""
        return len(self.errors) == 0 and self.total_indexed > 0
