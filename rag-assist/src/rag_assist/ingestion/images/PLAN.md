# PPT Content Extraction – 2-Step Framework Plan

This document describes the plan for the 2-step PPT content framework that runs in a **gated AWS environment with minimal permissions**. The logic is implemented in this folder and must not change; this plan is the reference for how it works and how to deploy it (e.g. on AWS SageMaker).

---

## 1. Overview

**Input:** One PPTX file + one PDF file (manual export of the same presentation).

**Goal:** Find and fetch content from both sources, map embeddings into a single vector store (OpenSearch), and retrieve unified text + image context by `document_id` and `slide_number`.

**Constraints:**
- Gated AWS environment (e.g. SageMaker, VPC, no arbitrary outbound).
- Minimal IAM permissions: Bedrock (Cohere + Titan), S3, OpenSearch only.
- No LibreOffice/headless conversion: PDF is **manually uploaded** for testing and production.

---

## 2. Two-Step Method

### Step 1 – PPT path (find → fetch → retrieve)

| Phase    | What happens | Implementation |
|----------|----------------|-----------------|
| **Find** | Parse PPTX and discover slides and text (titles, body, notes, tables). | `PPTXTextExtractor.extract(pptx_path)` → `PPTExtractionResult` with `slides: list[SlideTextContent]`. |
| **Fetch** | For each slide, get full text (title + body + notes + tables). | `SlideTextContent.full_text`; optional `slide_number`, `has_visual_content`. |
| **Retrieve** | Text is the **primary** source for RAG. | Stored in OpenSearch as `content_type=text`, `source=ppt`, linked by `document_id` + `slide_number`. |

**Embedding:** Cohere (via Bedrock) – one text embedding per slide.  
**Output:** One text document per slide in OpenSearch, with `text_embedding` and `slide_number`.

---

### Step 2 – PDF path (find → fetch → retrieve)

| Phase    | What happens | Implementation |
|----------|----------------|-----------------|
| **Find** | Open PDF and discover pages (1 page ≈ 1 slide). | `PDFContentExtractor.extract(pdf_path)` → `PDFExtractionResult` with `pages: list[PDFPageContent]`. |
| **Fetch** | Per page: (1) extracted text, (2) PNG render of the page. | `PDFPageContent.text_content`, `PDFPageContent.image_bytes`; `page_number` matches `slide_number`. |
| **Retrieve** | PDF text is **fallback** when PPT text is missing or for extra OCR-style content. PDF images are linked to slides by `page_number` = `slide_number`. | Text: only **non-duplicate** PDF text is indexed (see Deduplication). Images: always indexed; stored in S3, referenced in OpenSearch. |

**Embedding:**  
- Text: Cohere (same as Step 1).  
- Images: Amazon Titan Multimodal (via Bedrock).  

**Output:**  
- Text: OpenSearch docs with `content_type=text`, `source=pdf`, `slide_number=page_number`.  
- Images: Upload to S3 → OpenSearch docs with `content_type=image`, `image_s3_uri`, `image_embedding`, `slide_number=page_number`.

---

## 3. Mapping Embeddings and Linking

- **Same document:** Both steps use the same `document_id` (from PPTX or set explicitly) so that all content for one presentation is grouped.
- **Same slide index:** `slide_number` (PPT) = `page_number` (PDF). Retrieval uses `document_id` + `slide_number` to get both text and image for a slide.
- **Vector store:** OpenSearch index (e.g. `ppt-content`) holds:
  - Text docs: `text_embedding` (Cohere), `text_content`, `title`, `source` (ppt/pdf), `slide_number`.
  - Image docs: `image_embedding` (Titan), `image_s3_uri`, `slide_number`.
- **Linking:** No separate “link” step. Linking is by query: for a hit with `(document_id, slide_number)`, fetch the image doc with the same `document_id` and `slide_number` and `content_type=image` (see `content_retriever.py`).

---

## 4. Deduplication (Logic unchanged)

- **Goal:** Avoid indexing the same text twice (PPT and PDF often match).
- **Rule:** Compare PPT slide text and PDF page text by `slide_number` = `page_number`. If similarity ≥ threshold (e.g. 0.85), treat PDF text as duplicate and **do not** index that PDF page’s text.
- **Images:** Always indexed from PDF regardless of text duplicate; they are linked by `slide_number`.
- **Implementation:** `TextDeduplicator.get_unique_pdf_text(ppt_slides, pdf_pages)` returns only PDF pages whose text is sufficiently different from the corresponding PPT slide. The indexer uses this list for PDF text; PDF images are still taken from the full `pdf_result.pages`.

---

## 5. Failure Behavior (Logic unchanged)

- **PDF or image extraction fails:** Step 1 text (PPT) is still in OpenSearch; retrieval can return PPT text only (no image for that slide).
- **Bedrock (Cohere/Titan) fails:** Indexing of the affected slide/page fails; errors are collected and returned; other slides/pages can still be indexed.
- **S3 upload fails:** That page’s image is not stored; text for that slide (from PPT or PDF) can still be retrieved.

---

## 6. Minimal AWS Permissions (Gated environment)

Use a policy that allows only what this framework needs.

**Bedrock (embeddings):**
- `bedrock:InvokeModel` on:
  - Cohere embed model (e.g. `cohere.embed-english-v3` or your Cohere 4–based model ID).
  - Titan Multimodal (e.g. `amazon.titan-embed-image-v1`).

**S3 (image storage):**
- `s3:PutObject`, `s3:GetObject` on the bucket/prefix used for images (e.g. `arn:aws:s3:::your-bucket/images/*`).
- Optional: `s3:ListBucket`, `s3:DeleteObject` if you use list/delete in your code.

**OpenSearch:**
- `es:ESHttpGet`, `es:ESHttpPost`, `es:ESHttpPut`, `es:ESHttpDelete` on the OpenSearch domain (e.g. `arn:aws:es:region:account:domain/your-domain/*`).

**No other services** are required for this framework (no Lambda, no Step Functions, no SageMaker inference endpoints for this path – only Bedrock, S3, OpenSearch).

---

## 7. Implementation Files (No logic change)

| File | Role |
|------|------|
| `models.py` | Data classes: `SlideTextContent`, `PDFPageContent`, `PageTextContent`, `PageImageContent`, `PPTExtractionResult`, `PDFExtractionResult`, `IndexedTextDocument`, `IndexedImageDocument`, `IndexingResult`, `RetrievalResult`, `SlideContent`. |
| `ppt_text_extractor.py` | Step 1: PPT parsing → `PPTXTextExtractor.extract()` → `PPTExtractionResult`. |
| `pdf_content_extractor.py` | Step 2: PDF parsing → `PDFContentExtractor.extract()` / `extract_text_only()` / `extract_images_only()` → text + images per page. |
| `text_deduplicator.py` | Deduplication: `TextDeduplicator.find_duplicates()`, `get_unique_pdf_text()`. |
| `embedders.py` | Cohere text embedder, Titan Multimodal image embedder (Bedrock); lazy boto3 client. |
| `s3_store.py` | `S3ImageStore`: upload, presigned URL, download; lazy client. |
| `content_indexer.py` | Step 1: `index_ppt_text()` / `index_ppt_slides()`. Step 2: `index_pdf_content()`. Full run: `index_full_pipeline()`. OpenSearch index mapping. |
| `content_retriever.py` | Search by text query (Cohere embedding → OpenSearch); optional linked image by `document_id` + `slide_number`; presigned URL; `get_slide_content()`. |
| `__init__.py` | Re-exports public API; no logic. |

---

## 8. Workflow Summary

1. **Indexing (e.g. in SageMaker or a job):**
   - Ensure OpenSearch index exists (`PPTContentIndexer.ensure_index_exists()`).
   - Step 1: `indexer.index_ppt_text(pptx_path)` → PPT text embedded with Cohere and written to OpenSearch.
   - Step 2: `indexer.index_pdf_content(pdf_path, document_id=result1.document_id, ppt_slides=ppt_slides)` → unique PDF text + all PDF page images (Cohere + Titan), S3 upload, OpenSearch.
   - Or: `indexer.index_full_pipeline(pptx_path, pdf_path)` to run both steps with a single PPT extraction.

2. **Retrieval:**
   - `retriever.search(query, top_k=5, include_images=True)` → text hits + linked images by `slide_number`; presigned URLs for display.

3. **Gated environment:**
   - Only Bedrock, S3, and OpenSearch need to be reachable and allowed by IAM.
   - No change to the 2-step logic, deduplication, or embedding mapping described above.
