"""
MODULE: Document text parsing and extraction for PDF and DOCX.

@level-one-validation: High-throughput parsing offloaded to worker threadpool via run_in_threadpool. Features SHA256 parse caching. Tested in test_parser.py and test_performance.py.

#Scope-Of-Improvement: Add Tesseract OCR fallback for image-only scanned PDFs.
"""

import hashlib
import io
import logging

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from backend.models.schemas import PageText
from backend.security.validation import validate_character_count, validate_page_count

logger = logging.getLogger(__name__)

# Efficiency: In-memory parse cache indexed by SHA256 content hash
_PARSE_CACHE: dict[str, list[PageText]] = {}


# @risk-area: Scanned PDFs without extractable text layer will return no text; requires OCR engine for full coverage.
# #What: Extracts page-numbered text blocks from PDF stream using PyMuPDF
def _parse_pdf_sync(file_bytes: bytes) -> list[PageText]:
    """Extract text from PDF with page numbers. Runs in thread pool."""
    import pymupdf  # Import inside function to keep module import lightweight

    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse PDF: file may be corrupted or password-protected"
        )

    try:
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text").strip()
            if text:
                pages.append(PageText(page_number=page_num + 1, text=text))
        return pages
    finally:
        doc.close()


# #What: Extracts text paragraphs and table cell text from DOCX stream
def _parse_docx_sync(file_bytes: bytes) -> list[PageText]:
    """Extract text from DOCX with estimated page numbers."""
    import docx

    try:
        doc = docx.Document(io.BytesIO(file_bytes))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse DOCX: file may be corrupted"
        )

    all_paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = cell.text.strip()
                if text:
                    all_paragraphs.append(text)

    if not all_paragraphs:
        return []

    CHARS_PER_PAGE = 3000
    pages = []
    current_page_text = []
    current_char_count = 0
    current_page_num = 1

    for para in all_paragraphs:
        current_page_text.append(para)
        current_char_count += len(para)

        if current_char_count >= CHARS_PER_PAGE:
            pages.append(PageText(
                page_number=current_page_num,
                text="\n\n".join(current_page_text)
            ))
            current_page_text = []
            current_char_count = 0
            current_page_num += 1

    if current_page_text:
        pages.append(PageText(
            page_number=current_page_num,
            text="\n\n".join(current_page_text)
        ))

    return pages


# #Business-Intent: Converts uploaded binary files into page-aware text chunks for clause extraction.
async def parse_document(file_bytes: bytes, file_type: str) -> list[PageText]:
    """Parse a document into page-indexed text chunks with content hash caching.

    Efficiency: Checks SHA256 content hash cache for O(1) instant return.
    Runs CPU-bound parsing in a thread pool to avoid blocking the event loop.
    """
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    if content_hash in _PARSE_CACHE:
        logger.info(f"Efficiency: In-memory parse cache hit for SHA256 {content_hash[:8]}")
        return _PARSE_CACHE[content_hash]

    if file_type == "pdf":
        pages = await run_in_threadpool(_parse_pdf_sync, file_bytes)
    elif file_type == "docx":
        pages = await run_in_threadpool(_parse_docx_sync, file_bytes)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_type}"
        )

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from the document. It may be empty, image-only, or corrupted."
        )

    validate_page_count(len(pages))
    total_text = "\n".join(p.text for p in pages)
    validate_character_count(total_text)

    _PARSE_CACHE[content_hash] = pages
    logger.info(f"Parsed document: {len(pages)} pages, {len(total_text)} characters")
    return pages
