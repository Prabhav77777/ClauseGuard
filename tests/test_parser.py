"""Tests for document parsing and file validation.

Tests:
1. Parser extracts correct text + page numbers from fixture document
2. Oversized/mis-typed/corrupted files are rejected gracefully
"""

import pytest
from fastapi import HTTPException

from backend.security.validation import (
    validate_file_size,
    detect_file_type,
    validate_upload,
    validate_page_count,
    validate_character_count,
)


class TestFileValidation:
    """Test file type detection by magic bytes and size enforcement."""

    def test_detect_pdf_by_magic_bytes(self, sample_pdf_bytes):
        """PDF files are correctly detected by magic bytes, not extension."""
        file_type = detect_file_type(sample_pdf_bytes)
        assert file_type == "pdf"

    def test_detect_docx_by_magic_bytes(self, sample_docx_bytes):
        """DOCX files are correctly detected by ZIP + word/document.xml structure."""
        file_type = detect_file_type(sample_docx_bytes)
        assert file_type == "docx"

    def test_reject_wrong_file_type(self, wrong_type_bytes):
        """Text files are rejected with 415 Unsupported Media Type."""
        with pytest.raises(HTTPException) as exc_info:
            detect_file_type(wrong_type_bytes)
        assert exc_info.value.status_code == 415

    def test_reject_too_small_file(self):
        """Files smaller than 8 bytes are rejected as corrupted."""
        with pytest.raises(HTTPException) as exc_info:
            detect_file_type(b"tiny")
        assert exc_info.value.status_code == 400

    def test_reject_oversized_file(self):
        """Files exceeding MAX_FILE_SIZE_MB are rejected with 413."""
        # Create a fake large file (just enough bytes to exceed limit)
        large_bytes = b"x" * (11 * 1024 * 1024)  # 11MB, exceeds 10MB default
        with pytest.raises(HTTPException) as exc_info:
            validate_file_size(large_bytes)
        assert exc_info.value.status_code == 413

    def test_reject_excessive_pages(self):
        """Documents with too many pages are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_page_count(100)  # Exceeds default 50
        assert exc_info.value.status_code == 400

    def test_reject_excessive_characters(self):
        """Documents with too many characters are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            validate_character_count("x" * 600_000)  # Exceeds default 500K
        assert exc_info.value.status_code == 400

    def test_validate_upload_returns_pdf(self, sample_pdf_bytes):
        """validate_upload returns 'pdf' for valid PDF files."""
        result = validate_upload(sample_pdf_bytes, "test.pdf")
        assert result == "pdf"

    def test_validate_upload_returns_docx(self, sample_docx_bytes):
        """validate_upload returns 'docx' for valid DOCX files."""
        result = validate_upload(sample_docx_bytes, "test.docx")
        assert result == "docx"


class TestDocumentParser:
    """Test PDF and DOCX text extraction."""

    @pytest.mark.asyncio
    async def test_pdf_extracts_pages_with_numbers(self, sample_pdf_bytes):
        """Parser extracts text from each page with correct page numbers."""
        from backend.services.document_parser import parse_document

        pages = await parse_document(sample_pdf_bytes, "pdf")
        assert len(pages) >= 2, "Sample PDF should have at least 2 pages with text"
        assert pages[0].page_number == 1
        assert pages[1].page_number == 2
        # Verify known text is present
        full_text = " ".join(p.text for p in pages)
        assert "Employment Agreement" in full_text or "EMPLOYMENT AGREEMENT" in full_text

    @pytest.mark.asyncio
    async def test_pdf_contains_known_clauses(self, sample_pdf_bytes):
        """Parser extracts text containing known clause content."""
        from backend.services.document_parser import parse_document

        pages = await parse_document(sample_pdf_bytes, "pdf")
        full_text = " ".join(p.text for p in pages)
        # Known content from our fixture
        assert "120,000" in full_text, "Salary amount should be in extracted text"
        assert "probationary" in full_text.lower() or "probation" in full_text.lower()

    @pytest.mark.asyncio
    async def test_docx_extracts_text(self, sample_docx_bytes):
        """DOCX parser extracts paragraphs with estimated page numbers."""
        from backend.services.document_parser import parse_document

        pages = await parse_document(sample_docx_bytes, "docx")
        assert len(pages) >= 1
        full_text = " ".join(p.text for p in pages)
        assert "Service Agreement" in full_text or "SERVICE AGREEMENT" in full_text

    @pytest.mark.asyncio
    async def test_corrupted_pdf_raises_error(self, corrupted_pdf_bytes):
        """Corrupted PDFs raise a clear error, not a crash."""
        from backend.services.document_parser import parse_document

        with pytest.raises(HTTPException) as exc_info:
            await parse_document(corrupted_pdf_bytes, "pdf")
        assert exc_info.value.status_code == 400
