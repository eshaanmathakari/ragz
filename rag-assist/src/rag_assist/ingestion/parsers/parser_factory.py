"""Parser factory for routing documents to appropriate parsers."""

import os
from datetime import datetime
from pathlib import Path

import structlog

from rag_assist.ingestion.models import DocumentMetadata, DocumentType, ParsedDocument
from rag_assist.ingestion.parsers.base_parser import BaseParser
from rag_assist.ingestion.parsers.docx_parser import DOCXParser
from rag_assist.ingestion.parsers.pdf_parser import PDFParser
from rag_assist.ingestion.parsers.pptx_parser import PPTXParser

logger = structlog.get_logger(__name__)


class ParserFactory:
    """Factory for creating and managing document parsers.

    Routes documents to appropriate parser based on file type.
    """

    def __init__(
        self,
        use_textract_fallback: bool = True,
        include_speaker_notes: bool = True,
    ):
        """Initialize parser factory.

        Args:
            use_textract_fallback: Use Textract for scanned PDFs.
            include_speaker_notes: Include speaker notes in PPTX parsing.
        """
        self._parsers: dict[DocumentType, BaseParser] = {
            DocumentType.PDF: PDFParser(use_textract_fallback=use_textract_fallback),
            DocumentType.PPTX: PPTXParser(include_speaker_notes=include_speaker_notes),
            DocumentType.DOCX: DOCXParser(),
        }

    def get_parser(self, file_path: str | Path) -> BaseParser | None:
        """Get appropriate parser for file.

        Args:
            file_path: Path to document file.

        Returns:
            Parser instance or None if no suitable parser found.
        """
        path = Path(file_path)
        doc_type = DocumentType.from_extension(path.suffix)

        if doc_type == DocumentType.UNKNOWN:
            logger.warning(f"No parser available for file type: {path.suffix}")
            return None

        return self._parsers.get(doc_type)

    def parse(self, file_path: str | Path, s3_uri: str = "") -> ParsedDocument | None:
        """Parse a document file.

        Args:
            file_path: Path to document file.
            s3_uri: Optional S3 URI for the source file.

        Returns:
            ParsedDocument or None if parsing failed.
        """
        path = Path(file_path)

        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Get parser
        parser = self.get_parser(path)
        if not parser:
            return None

        # Build metadata from path
        path_metadata = BaseParser.extract_metadata_from_path(path)

        # Get file stats
        stat = path.stat()

        metadata = DocumentMetadata(
            file_path=str(path.absolute()),
            file_type=DocumentType.from_extension(path.suffix),
            filename=path.name,
            s3_uri=s3_uri,
            module_name=path_metadata["module_name"],
            folder_path=path_metadata["folder_path"],
            week_number=path_metadata["week_number"],
            file_size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )

        return parser.parse(path, metadata)

    def parse_batch(
        self,
        file_paths: list[str | Path],
        s3_uri_map: dict[str, str] | None = None,
    ) -> list[ParsedDocument]:
        """Parse multiple documents.

        Args:
            file_paths: List of file paths to parse.
            s3_uri_map: Optional mapping of file paths to S3 URIs.

        Returns:
            List of successfully parsed documents.
        """
        s3_uri_map = s3_uri_map or {}
        results = []

        for file_path in file_paths:
            path_str = str(file_path)
            s3_uri = s3_uri_map.get(path_str, "")

            try:
                result = self.parse(file_path, s3_uri)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {str(e)}")

        return results

    @staticmethod
    def discover_documents(
        directory: str | Path,
        recursive: bool = True,
    ) -> list[Path]:
        """Discover parseable documents in a directory.

        Args:
            directory: Directory to search.
            recursive: Search subdirectories.

        Returns:
            List of document file paths.
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            logger.error(f"Not a directory: {directory}")
            return []

        # Supported extensions
        extensions = {".pdf", ".pptx", ".ppt", ".docx", ".doc"}

        documents = []

        if recursive:
            for ext in extensions:
                documents.extend(dir_path.rglob(f"*{ext}"))
        else:
            for ext in extensions:
                documents.extend(dir_path.glob(f"*{ext}"))

        # Sort by path for consistent ordering
        documents.sort()

        logger.info(f"Discovered {len(documents)} documents in {directory}")
        return documents

    def supported_extensions(self) -> list[str]:
        """Get list of supported file extensions.

        Returns:
            List of supported extensions (e.g., ['.pdf', '.pptx']).
        """
        return [".pdf", ".pptx", ".ppt", ".docx", ".doc"]
