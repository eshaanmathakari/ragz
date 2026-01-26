"""PDF parser using PyMuPDF with Textract fallback for scanned documents."""

from pathlib import Path

import fitz  # PyMuPDF
import structlog

from rag_assist.config import get_textract_client
from rag_assist.ingestion.models import (
    DocumentMetadata,
    DocumentType,
    PageContent,
    ParsedDocument,
    TextBlock,
)
from rag_assist.ingestion.parsers.base_parser import BaseParser

logger = structlog.get_logger(__name__)


class PDFParser(BaseParser):
    """Hybrid PDF parser using PyMuPDF with Textract fallback.

    Strategy:
    1. First attempt native text extraction with PyMuPDF
    2. Detect pages with low text density (likely scanned)
    3. Use Textract only for problematic pages
    """

    supported_types = [DocumentType.PDF]

    def __init__(
        self,
        text_density_threshold: float = 0.01,
        use_textract_fallback: bool = True,
    ):
        """Initialize PDF parser.

        Args:
            text_density_threshold: Minimum text density (chars per pixel area)
                to consider a page as text-based. Pages below this use Textract.
            use_textract_fallback: Whether to use Textract for scanned pages.
        """
        self.text_density_threshold = text_density_threshold
        self.use_textract_fallback = use_textract_fallback
        self._textract_client = None

    @property
    def textract_client(self):
        """Lazy-load Textract client."""
        if self._textract_client is None and self.use_textract_fallback:
            self._textract_client = get_textract_client()
        return self._textract_client

    def can_parse(self, file_path: str | Path) -> bool:
        """Check if file is a PDF."""
        path = Path(file_path)
        return path.suffix.lower() == ".pdf"

    def parse(self, file_path: str | Path, metadata: DocumentMetadata) -> ParsedDocument:
        """Parse PDF document.

        Args:
            file_path: Path to PDF file.
            metadata: Document metadata.

        Returns:
            ParsedDocument with extracted content.
        """
        self.log_parsing_start(file_path)
        path = Path(file_path)
        pages: list[PageContent] = []
        errors: list[str] = []
        is_scanned = False

        try:
            doc = fitz.open(str(path))
            metadata.total_pages = len(doc)

            for page_num in range(len(doc)):
                page = doc[page_num]

                try:
                    page_content = self._extract_page_native(page, page_num + 1)

                    # Check if page appears to be scanned (low text density)
                    if self._is_page_scanned(page, page_content):
                        is_scanned = True
                        if self.use_textract_fallback:
                            logger.info(
                                "Page appears scanned, using Textract",
                                page_number=page_num + 1,
                            )
                            page_content = self._extract_page_textract(
                                path, page_num + 1
                            )

                    pages.append(page_content)

                except Exception as e:
                    error_msg = f"Error parsing page {page_num + 1}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
                    # Add empty page content to maintain page numbering
                    pages.append(
                        PageContent(
                            page_number=page_num + 1,
                            text="",
                            extraction_method="error",
                            confidence=0.0,
                        )
                    )

            doc.close()

            # Update metadata
            metadata.is_scanned = is_scanned
            metadata.extraction_method = "textract" if is_scanned else "native"

        except Exception as e:
            self.log_parsing_error(file_path, e)
            errors.append(f"Failed to open PDF: {str(e)}")

        result = ParsedDocument(
            metadata=metadata,
            content=pages,
            extraction_method=metadata.extraction_method,
            processing_errors=errors,
        )

        self.log_parsing_complete(file_path, result)
        return result

    def _extract_page_native(self, page: fitz.Page, page_number: int) -> PageContent:
        """Extract content from page using PyMuPDF native extraction.

        Args:
            page: PyMuPDF page object.
            page_number: Page number (1-indexed).

        Returns:
            PageContent with extracted text and blocks.
        """
        # Get raw text
        text = page.get_text("text")
        text = self.normalize_text(text)

        # Get text blocks with positions for structure detection
        blocks_data = page.get_text("dict")["blocks"]
        text_blocks = []

        for block in blocks_data:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text:
                            text_blocks.append(
                                TextBlock(
                                    text=span_text,
                                    font_size=span.get("size", 12),
                                    is_bold="bold" in span.get("font", "").lower(),
                                    is_heading=span.get("size", 12) > 14,
                                    block_type="paragraph",
                                )
                            )

        # Extract tables (if any)
        tables = self._extract_tables(page)

        return PageContent(
            page_number=page_number,
            text=text,
            text_blocks=text_blocks,
            tables=tables,
            extraction_method="native",
            confidence=1.0,
        )

    def _extract_tables(self, page: fitz.Page) -> list[list[list[str]]]:
        """Extract tables from a PDF page.

        Args:
            page: PyMuPDF page object.

        Returns:
            List of tables, each table is a list of rows, each row is a list of cells.
        """
        tables = []
        try:
            # PyMuPDF table extraction (available in newer versions)
            tabs = page.find_tables()
            for tab in tabs:
                table_data = tab.extract()
                if table_data:
                    tables.append(table_data)
        except Exception:
            # Table extraction not available or failed
            pass
        return tables

    def _is_page_scanned(self, page: fitz.Page, content: PageContent) -> bool:
        """Determine if a page is likely scanned (image-based).

        Args:
            page: PyMuPDF page object.
            content: Extracted page content.

        Returns:
            True if page appears to be scanned.
        """
        # Calculate text density
        page_area = page.rect.width * page.rect.height
        if page_area == 0:
            return False

        text_chars = len(content.text.replace(" ", "").replace("\n", ""))
        text_density = text_chars / page_area

        # Check for images that cover most of the page
        image_list = page.get_images()
        has_large_image = False
        for img in image_list:
            try:
                img_rect = page.get_image_rects(img[0])
                if img_rect:
                    for rect in img_rect:
                        img_area = rect.width * rect.height
                        if img_area / page_area > 0.5:  # Image covers >50% of page
                            has_large_image = True
                            break
            except Exception:
                pass

        # Page is likely scanned if low text density and has large image
        return text_density < self.text_density_threshold and has_large_image

    def _extract_page_textract(self, file_path: Path, page_number: int) -> PageContent:
        """Extract page content using Amazon Textract.

        Args:
            file_path: Path to PDF file.
            page_number: Page number to extract (1-indexed).

        Returns:
            PageContent with Textract-extracted text.
        """
        if not self.textract_client:
            return PageContent(
                page_number=page_number,
                text="",
                extraction_method="textract_unavailable",
                confidence=0.0,
            )

        try:
            # Read the PDF file
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            # Call Textract for document analysis
            response = self.textract_client.analyze_document(
                Document={"Bytes": pdf_bytes},
                FeatureTypes=["TABLES", "FORMS"],
            )

            # Extract text from Textract response
            text_parts = []
            text_blocks = []
            confidence_sum = 0.0
            confidence_count = 0

            for block in response.get("Blocks", []):
                if block.get("BlockType") == "LINE":
                    block_text = block.get("Text", "")
                    confidence = block.get("Confidence", 0) / 100

                    text_parts.append(block_text)
                    text_blocks.append(
                        TextBlock(
                            text=block_text,
                            block_type="paragraph",
                        )
                    )

                    confidence_sum += confidence
                    confidence_count += 1

            avg_confidence = (
                confidence_sum / confidence_count if confidence_count > 0 else 0.0
            )

            return PageContent(
                page_number=page_number,
                text=self.normalize_text("\n".join(text_parts)),
                text_blocks=text_blocks,
                extraction_method="textract",
                confidence=avg_confidence,
            )

        except Exception as e:
            logger.error(
                "Textract extraction failed",
                page_number=page_number,
                error=str(e),
            )
            return PageContent(
                page_number=page_number,
                text="",
                extraction_method="textract_error",
                confidence=0.0,
            )
