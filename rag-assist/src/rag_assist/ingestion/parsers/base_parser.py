"""Base parser interface for document parsing."""

import re
from abc import ABC, abstractmethod
from pathlib import Path

import structlog

from rag_assist.ingestion.models import DocumentMetadata, DocumentType, ParsedDocument

logger = structlog.get_logger(__name__)


class BaseParser(ABC):
    """Abstract base class for document parsers."""

    supported_types: list[DocumentType] = []

    @abstractmethod
    def parse(self, file_path: str | Path, metadata: DocumentMetadata) -> ParsedDocument:
        """Parse a document and extract content.

        Args:
            file_path: Path to the document file.
            metadata: Pre-populated document metadata.

        Returns:
            ParsedDocument containing extracted content and metadata.
        """
        pass

    @abstractmethod
    def can_parse(self, file_path: str | Path) -> bool:
        """Check if this parser can handle the given file.

        Args:
            file_path: Path to the document file.

        Returns:
            True if the parser can handle this file type.
        """
        pass

    @staticmethod
    def extract_metadata_from_path(file_path: str | Path) -> dict:
        """Extract metadata from file path (folder structure).

        Handles folder names like:
        - "week 1/subfolder/file.pdf"
        - "Week 2/content/slides.pptx"
        - "APAC Schedule and related Info/doc.docx"

        Args:
            file_path: Path to the document file.

        Returns:
            Dictionary with extracted metadata.
        """
        path = Path(file_path)
        parts = path.parts

        metadata = {
            "filename": path.name,
            "folder_path": str(path.parent),
            "module_name": "",
            "week_number": None,
        }

        # Try to extract week number from path
        week_pattern = re.compile(r"week\s*(\d+)", re.IGNORECASE)

        for part in parts:
            match = week_pattern.search(part)
            if match:
                metadata["week_number"] = int(match.group(1))
                metadata["module_name"] = part
                break

        # If no week found, use the first non-root folder as module name
        if not metadata["module_name"] and len(parts) > 1:
            # Skip common root folders
            skip_folders = {"data", "documents", "files", "content"}
            for part in parts[:-1]:  # Exclude filename
                if part.lower() not in skip_folders:
                    metadata["module_name"] = part
                    break

        return metadata

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for consistent processing.

        Args:
            text: Raw text to normalize.

        Returns:
            Normalized text.
        """
        if not text:
            return ""

        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)

        # Remove control characters except newlines
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

        # Normalize unicode characters
        text = text.encode("utf-8", errors="ignore").decode("utf-8")

        return text.strip()

    def log_parsing_start(self, file_path: str | Path) -> None:
        """Log the start of parsing."""
        logger.info(
            "Starting document parsing",
            file_path=str(file_path),
            parser=self.__class__.__name__,
        )

    def log_parsing_complete(
        self, file_path: str | Path, result: ParsedDocument
    ) -> None:
        """Log parsing completion."""
        logger.info(
            "Document parsing complete",
            file_path=str(file_path),
            parser=self.__class__.__name__,
            content_count=len(result.content),
            errors=len(result.processing_errors),
        )

    def log_parsing_error(self, file_path: str | Path, error: Exception) -> None:
        """Log parsing error."""
        logger.error(
            "Document parsing failed",
            file_path=str(file_path),
            parser=self.__class__.__name__,
            error=str(error),
            exc_info=True,
        )
