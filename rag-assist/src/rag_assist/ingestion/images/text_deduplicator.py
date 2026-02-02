"""Text deduplication between PPT and PDF content.

Since both PPT and PDF contain similar text content, we need to detect
and skip duplicates to avoid indexing the same content twice.

Strategy:
1. Match PPT slide_number with PDF page_number
2. Compare text content using similarity (Jaccard or normalized edit distance)
3. If similarity > threshold (e.g., 90%), mark as duplicate
4. Only index PDF text that adds new information (e.g., OCR'd text from images)
5. Always index images regardless of text duplication
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from models import PDFPageContent, PageTextContent, SlideTextContent

# Try structlog, fallback to standard logging
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


@dataclass
class DuplicateInfo:
    """Information about a detected duplicate."""

    slide_number: int
    page_number: int
    ppt_text_length: int
    pdf_text_length: int
    similarity_score: float
    is_duplicate: bool


class TextDeduplicator:
    """Detect and skip duplicate text between PPT and PDF.

    Usage:
        deduplicator = TextDeduplicator(similarity_threshold=0.9)

        # Find which pages are duplicates
        duplicates = deduplicator.find_duplicates(ppt_slides, pdf_pages)

        # Get only unique PDF text (not in PPT)
        unique_text = deduplicator.get_unique_pdf_text(ppt_slides, pdf_pages)
    """

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialize deduplicator.

        Args:
            similarity_threshold: Similarity score above which text is
                                 considered duplicate (0.0 to 1.0).
        """
        self.threshold = similarity_threshold

    def find_duplicates(
        self,
        ppt_slides: list[SlideTextContent],
        pdf_pages: list[PDFPageContent] | list[PageTextContent],
    ) -> list[DuplicateInfo]:
        """Find matching slide/page pairs by text similarity.

        Args:
            ppt_slides: Slides extracted from PPT.
            pdf_pages: Pages extracted from PDF.

        Returns:
            List of DuplicateInfo for each matched pair.
        """
        # Build lookup by slide/page number
        ppt_by_slide = {s.slide_number: s for s in ppt_slides}
        pdf_by_page = {p.page_number: p for p in pdf_pages}

        results: list[DuplicateInfo] = []

        # Compare matching slide/page numbers
        for page_num, pdf_page in pdf_by_page.items():
            ppt_slide = ppt_by_slide.get(page_num)

            if ppt_slide is None:
                # No matching PPT slide - PDF text is unique
                pdf_text = self._get_text(pdf_page)
                results.append(
                    DuplicateInfo(
                        slide_number=page_num,
                        page_number=page_num,
                        ppt_text_length=0,
                        pdf_text_length=len(pdf_text),
                        similarity_score=0.0,
                        is_duplicate=False,
                    )
                )
                continue

            # Compare text content
            ppt_text = ppt_slide.full_text
            pdf_text = self._get_text(pdf_page)

            similarity = self._calculate_similarity(ppt_text, pdf_text)
            is_duplicate = similarity >= self.threshold

            results.append(
                DuplicateInfo(
                    slide_number=ppt_slide.slide_number,
                    page_number=page_num,
                    ppt_text_length=len(ppt_text),
                    pdf_text_length=len(pdf_text),
                    similarity_score=similarity,
                    is_duplicate=is_duplicate,
                )
            )

            logger.debug(
                "Compared slide/page",
                slide=page_num,
                ppt_len=len(ppt_text),
                pdf_len=len(pdf_text),
                similarity=f"{similarity:.2f}",
                is_duplicate=is_duplicate,
            )

        return results

    def get_unique_pdf_text(
        self,
        ppt_slides: list[SlideTextContent],
        pdf_pages: list[PDFPageContent] | list[PageTextContent],
    ) -> list[PageTextContent]:
        """Get PDF text that doesn't duplicate PPT text.

        Only returns PDF pages whose text is significantly different
        from the corresponding PPT slide (e.g., additional OCR'd text
        from images that wasn't in the original PPT).

        Args:
            ppt_slides: Slides extracted from PPT.
            pdf_pages: Pages extracted from PDF.

        Returns:
            List of PageTextContent for non-duplicate pages.
        """
        duplicates = self.find_duplicates(ppt_slides, pdf_pages)
        duplicate_pages = {d.page_number for d in duplicates if d.is_duplicate}

        unique_text: list[PageTextContent] = []

        for pdf_page in pdf_pages:
            if pdf_page.page_number not in duplicate_pages:
                text = self._get_text(pdf_page)
                if text.strip():  # Only include if there's actual text
                    unique_text.append(
                        PageTextContent(
                            document_id=pdf_page.document_id,
                            filename=pdf_page.filename,
                            page_number=pdf_page.page_number,
                            text_content=text,
                        )
                    )

        logger.info(
            "Deduplication complete",
            total_ppt_slides=len(ppt_slides),
            total_pdf_pages=len(pdf_pages),
            duplicates=len(duplicate_pages),
            unique_pdf_pages=len(unique_text),
        )

        return unique_text

    def get_pages_needing_image_only(
        self,
        ppt_slides: list[SlideTextContent],
        pdf_pages: list[PDFPageContent],
    ) -> list[int]:
        """Get page numbers where only image needs to be indexed (text is duplicate).

        For these pages, the PPT text is sufficient, but we still want the
        PDF image for visual content.

        Args:
            ppt_slides: Slides extracted from PPT.
            pdf_pages: Pages extracted from PDF.

        Returns:
            List of page numbers where text is duplicate but image is needed.
        """
        duplicates = self.find_duplicates(ppt_slides, pdf_pages)
        return [d.page_number for d in duplicates if d.is_duplicate]

    def _get_text(self, page: PDFPageContent | PageTextContent) -> str:
        """Extract text from a PDF page content object."""
        if isinstance(page, PDFPageContent):
            return page.text_content
        return page.text_content

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using Jaccard similarity.

        Uses word-level comparison after normalization.

        Args:
            text1: First text.
            text2: Second text.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        # Normalize texts
        words1 = self._tokenize(text1)
        words2 = self._tokenize(text2)

        if not words1 and not words2:
            return 1.0  # Both empty = identical
        if not words1 or not words2:
            return 0.0  # One empty, one not = different

        # Jaccard similarity: intersection / union
        set1 = set(words1)
        set2 = set(words2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into normalized words."""
        if not text:
            return []

        # Lowercase and extract words
        text = text.lower()
        words = re.findall(r"\b\w+\b", text)

        # Remove very short words and common stop words
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        words = [w for w in words if len(w) > 2 and w not in stop_words]

        return words


def get_text_for_indexing(
    ppt_slides: list[SlideTextContent],
    pdf_pages: list[PDFPageContent],
    similarity_threshold: float = 0.85,
) -> tuple[list[SlideTextContent], list[PageTextContent]]:
    """Get all text that should be indexed (PPT text + unique PDF text).

    This is a convenience function that:
    1. Returns all PPT slides (primary text source)
    2. Returns PDF pages whose text differs significantly from PPT
       (e.g., OCR'd text from images)

    Args:
        ppt_slides: Slides extracted from PPT.
        pdf_pages: Pages extracted from PDF.
        similarity_threshold: Threshold for duplicate detection.

    Returns:
        Tuple of (ppt_slides_to_index, unique_pdf_text_to_index).
    """
    deduplicator = TextDeduplicator(similarity_threshold=similarity_threshold)
    unique_pdf_text = deduplicator.get_unique_pdf_text(ppt_slides, pdf_pages)

    return ppt_slides, unique_pdf_text
