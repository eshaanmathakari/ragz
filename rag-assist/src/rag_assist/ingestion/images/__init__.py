"""Image extraction module for PPTX files (v2 - PDF Approach).

This module provides tools to:
1. Detect slides containing images, SmartArt, and charts
2. Convert PPTX to PDF using LibreOffice
3. Extract specific PDF pages as PNG images using PyMuPDF
4. Upload images to S3
5. Create mappings between images and slide numbers

This module is designed to be portable and work standalone on SageMaker.
"""

from .pptx_image_extractor import (
    # Data classes
    ImageInfo,
    SlideImageMapping,
    ExtractionResult,
    # Core classes
    PPTXImageDetector,
    PPTXtoPDFConverter,
    PDFPageExtractor,
    S3ImageStore,
    # Pipeline function
    extract_pptx_images,
)

__all__ = [
    "ImageInfo",
    "SlideImageMapping",
    "ExtractionResult",
    "PPTXImageDetector",
    "PPTXtoPDFConverter",
    "PDFPageExtractor",
    "S3ImageStore",
    "extract_pptx_images",
]
