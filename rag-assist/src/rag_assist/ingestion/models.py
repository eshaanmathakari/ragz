"""Data models for document ingestion pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DocumentType(Enum):
    """Supported document types."""

    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    UNKNOWN = "unknown"

    @classmethod
    def from_extension(cls, extension: str) -> "DocumentType":
        """Get document type from file extension."""
        ext_map = {
            ".pdf": cls.PDF,
            ".pptx": cls.PPTX,
            ".ppt": cls.PPTX,
            ".docx": cls.DOCX,
            ".doc": cls.DOCX,
        }
        return ext_map.get(extension.lower(), cls.UNKNOWN)


@dataclass
class TextBlock:
    """A block of text with formatting context."""

    text: str
    level: int = 0  # Indentation/hierarchy level
    font_size: float | None = None
    is_bold: bool = False
    is_heading: bool = False
    block_type: str = "paragraph"  # paragraph, list_item, table_cell


@dataclass
class PageContent:
    """Content extracted from a PDF page."""

    page_number: int
    text: str
    text_blocks: list[TextBlock] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    extraction_method: str = "native"  # native or textract
    confidence: float = 1.0


@dataclass
class SlideContent:
    """Content extracted from a PowerPoint slide."""

    slide_number: int
    title: str = ""
    body_text: list[TextBlock] = field(default_factory=list)
    speaker_notes: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    layout_type: str = ""

    @property
    def full_text(self) -> str:
        """Get all text content from the slide."""
        parts = []
        if self.title:
            parts.append(self.title)
        for block in self.body_text:
            if block.text.strip():
                parts.append(block.text)
        return "\n".join(parts)


@dataclass
class SectionContent:
    """Content extracted from a DOCX section (heading + content)."""

    heading: str = ""
    heading_level: int = 0
    content: list[TextBlock] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    hyperlinks: list[dict[str, str]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Get all text content from the section."""
        parts = []
        if self.heading:
            parts.append(self.heading)
        for block in self.content:
            if block.text.strip():
                parts.append(block.text)
        return "\n".join(parts)


@dataclass
class DocumentMetadata:
    """Metadata for a processed document."""

    file_path: str
    file_type: DocumentType
    filename: str
    s3_uri: str = ""

    # Folder-derived metadata
    module_name: str = ""
    folder_path: str = ""
    week_number: int | None = None

    # File metadata
    file_size_bytes: int = 0
    created_at: datetime | None = None
    modified_at: datetime | None = None

    # Processing metadata
    total_pages: int = 0
    total_slides: int = 0
    is_scanned: bool = False
    extraction_method: str = "native"


@dataclass
class ParsedDocument:
    """A fully parsed document with content and metadata."""

    metadata: DocumentMetadata
    content: list[PageContent] | list[SlideContent] | list[SectionContent]
    extraction_method: str = "native"
    processing_errors: list[str] = field(default_factory=list)

    @property
    def total_text(self) -> str:
        """Get all text content from the document."""
        if not self.content:
            return ""

        if isinstance(self.content[0], PageContent):
            return "\n\n".join(page.text for page in self.content)
        elif isinstance(self.content[0], SlideContent):
            return "\n\n".join(slide.full_text for slide in self.content)
        elif isinstance(self.content[0], SectionContent):
            return "\n\n".join(section.full_text for section in self.content)
        return ""

    @property
    def is_successful(self) -> bool:
        """Check if parsing was successful."""
        return len(self.content) > 0 and len(self.processing_errors) == 0


@dataclass
class ChunkMetadata:
    """Metadata for a text chunk ready for indexing."""

    chunk_id: str
    document_id: str

    # Source location
    filename: str
    file_type: str
    s3_uri: str
    module_name: str
    folder_path: str
    week_number: int | None

    # Position in document
    page_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None
    heading_hierarchy: list[str] = field(default_factory=list)
    chunk_index: int = 0
    position_in_section: str = "middle"  # beginning, middle, end
    content_type: str = "body"  # title, body, table, list, note

    # Semantic metadata
    keywords: list[str] = field(default_factory=list)
    entities: list[dict[str, str]] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    document_intent: str = ""

    # Deduplication
    content_hash: str = ""
    semantic_fingerprint: str = ""
    canonical_chunk_id: str | None = None

    # Technical
    char_count: int = 0
    token_count: int = 0
    extraction_method: str = "native"
    extraction_confidence: float = 1.0

    # Timestamps
    ingested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TextChunk:
    """A chunk of text ready for embedding and indexing."""

    text: str
    metadata: ChunkMetadata
    embedding: list[float] | None = None
