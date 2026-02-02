"""Step 2: PDF Content Extraction using PyMuPDF.

This module extracts BOTH text AND images from PDF pages:
- Text content from each page
- PNG render of each page (for visual content like SmartArt, charts)

page_number in PDF corresponds to slide_number in PPT for linking.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from models import (
    PDFExtractionResult,
    PDFPageContent,
    PageImageContent,
    PageTextContent,
)

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class PDFContentExtractor:
    """Extract text AND images from PDF pages.

    Usage:
        extractor = PDFContentExtractor(dpi=150)

        # Extract both text and images
        result = extractor.extract("presentation.pdf")

        for page in result.pages:
            print(f"Page {page.page_number}: {page.text_content[:100]}...")
            if page.has_image:
                # Save or upload page.image_bytes

        # Or extract separately
        text_pages = extractor.extract_text_only("presentation.pdf")
        image_pages = extractor.extract_images_only("presentation.pdf")
    """

    def __init__(self, dpi: int = 150):
        """Initialize extractor.

        Args:
            dpi: Resolution for image rendering.
                 150 = good for web, 300 = good for print.
        """
        self.dpi = dpi
        self.zoom = dpi / 72  # PDF default is 72 DPI

    def extract(
        self,
        pdf_path: str | Path,
        document_id: str | None = None,
        page_numbers: list[int] | None = None,
    ) -> PDFExtractionResult:
        """Extract text AND images from PDF pages.

        Args:
            pdf_path: Path to PDF file.
            document_id: Document identifier. Auto-generated if not provided.
            page_numbers: Specific pages to extract (1-indexed).
                         None = all pages.

        Returns:
            PDFExtractionResult with all page content.
        """
        import fitz  # PyMuPDF

        path = Path(pdf_path)
        filename = path.name

        if document_id is None:
            document_id = self._generate_document_id(path)

        pages: list[PDFPageContent] = []
        errors: list[str] = []

        logger.info("Extracting content from PDF", filename=filename, dpi=self.dpi)

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)

            # Determine which pages to extract
            if page_numbers is None:
                page_numbers = list(range(1, total_pages + 1))

            for page_num in page_numbers:
                if page_num < 1 or page_num > total_pages:
                    errors.append(f"Invalid page number: {page_num}")
                    continue

                try:
                    page_content = self._extract_page(
                        doc, page_num, document_id, filename
                    )
                    pages.append(page_content)
                except Exception as e:
                    error_msg = f"Error extracting page {page_num}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

            doc.close()

            logger.info(
                "PDF extraction complete",
                filename=filename,
                total_pages=total_pages,
                pages_extracted=len(pages),
                errors=len(errors),
            )

        except Exception as e:
            error_msg = f"Failed to open PDF: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
            total_pages = 0

        return PDFExtractionResult(
            document_id=document_id,
            filename=filename,
            total_pages=total_pages,
            pages=pages,
            errors=errors,
        )

    def extract_text_only(
        self,
        pdf_path: str | Path,
        document_id: str | None = None,
        page_numbers: list[int] | None = None,
    ) -> list[PageTextContent]:
        """Extract just text from PDF (no images).

        Args:
            pdf_path: Path to PDF file.
            document_id: Document identifier.
            page_numbers: Specific pages to extract (1-indexed).

        Returns:
            List of PageTextContent with text from each page.
        """
        import fitz

        path = Path(pdf_path)
        filename = path.name

        if document_id is None:
            document_id = self._generate_document_id(path)

        text_pages: list[PageTextContent] = []

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)

            if page_numbers is None:
                page_numbers = list(range(1, total_pages + 1))

            for page_num in page_numbers:
                if page_num < 1 or page_num > total_pages:
                    continue

                try:
                    page = doc[page_num - 1]
                    text_content = page.get_text()

                    text_pages.append(
                        PageTextContent(
                            document_id=document_id,
                            filename=filename,
                            page_number=page_num,
                            text_content=text_content.strip(),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num}: {e}")

            doc.close()

        except Exception as e:
            logger.error(f"Failed to open PDF for text extraction: {e}")

        return text_pages

    def extract_images_only(
        self,
        pdf_path: str | Path,
        document_id: str | None = None,
        page_numbers: list[int] | None = None,
    ) -> list[PageImageContent]:
        """Extract just images from PDF (no text).

        Args:
            pdf_path: Path to PDF file.
            document_id: Document identifier.
            page_numbers: Specific pages to extract (1-indexed).

        Returns:
            List of PageImageContent with PNG renders.
        """
        import fitz

        path = Path(pdf_path)
        filename = path.name

        if document_id is None:
            document_id = self._generate_document_id(path)

        image_pages: list[PageImageContent] = []

        try:
            doc = fitz.open(str(path))
            total_pages = len(doc)

            if page_numbers is None:
                page_numbers = list(range(1, total_pages + 1))

            for page_num in page_numbers:
                if page_num < 1 or page_num > total_pages:
                    continue

                try:
                    page = doc[page_num - 1]
                    mat = fitz.Matrix(self.zoom, self.zoom)
                    pix = page.get_pixmap(matrix=mat)
                    img_bytes = pix.tobytes("png")

                    image_pages.append(
                        PageImageContent(
                            document_id=document_id,
                            filename=filename,
                            page_number=page_num,
                            image_bytes=img_bytes,
                            width_px=pix.width,
                            height_px=pix.height,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error extracting image from page {page_num}: {e}")

            doc.close()

        except Exception as e:
            logger.error(f"Failed to open PDF for image extraction: {e}")

        return image_pages

    def _extract_page(
        self, doc, page_num: int, document_id: str, filename: str
    ) -> PDFPageContent:
        """Extract both text and image from a single page."""
        import fitz

        page = doc[page_num - 1]  # 0-indexed

        # Extract text
        text_content = page.get_text().strip()

        # Render as PNG
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        logger.info(
            "Extracted page",
            page=page_num,
            text_len=len(text_content),
            img_width=pix.width,
            img_height=pix.height,
            img_size_kb=len(img_bytes) // 1024,
        )

        return PDFPageContent(
            document_id=document_id,
            filename=filename,
            page_number=page_num,
            text_content=text_content,
            image_bytes=img_bytes,
            width_px=pix.width,
            height_px=pix.height,
        )

    def get_page_count(self, pdf_path: str | Path) -> int:
        """Get total number of pages in PDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Number of pages.
        """
        import fitz

        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count

    def _generate_document_id(self, path: Path) -> str:
        """Generate document ID from file path and content hash."""
        try:
            content = path.read_bytes()
            hash_digest = hashlib.sha256(content).hexdigest()[:12]
            return f"{path.stem}_{hash_digest}"
        except Exception:
            return f"{path.stem}_{uuid.uuid4().hex[:12]}"
