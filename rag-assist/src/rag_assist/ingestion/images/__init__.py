"""Image extraction module for PPTX files.

This module provides tools to:
- Detect slides containing images, SmartArt, and charts
- Extract/render slides as PNG images
- Upload images to S3
- Create mappings between images and slide numbers

This module is designed to be portable and work standalone.
"""

# Use relative import to avoid loading the entire rag_assist package
from .pptx_image_extractor import (
    ImageInfo,
    SlideImageMapping,
    ExtractionResult,
    PPTXImageDetector,
    PPTXImageExtractor,
    S3ImageStore,
    ImageMapper,
    extract_images_from_pptx,
)

__all__ = [
    "ImageInfo",
    "SlideImageMapping",
    "ExtractionResult",
    "PPTXImageDetector",
    "PPTXImageExtractor",
    "S3ImageStore",
    "ImageMapper",
    "extract_images_from_pptx",
]
