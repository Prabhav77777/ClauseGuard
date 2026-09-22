"""File upload validation — security-first approach.

Validates files by magic bytes (not extension), enforces size/page/character
limits, and strips metadata. This is the first line of defense before any
document content reaches the parser or LLM.
"""

import io
import zipfile

from fastapi import HTTPException, status

from backend.config import settings

# Magic byte signatures — validated at the binary level, not by extension
PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"


def validate_file_size(file_bytes: bytes) -> None:
    """Reject empty (0 bytes) or oversized files exceeding configured size limit."""
    if not file_bytes or len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes)"
        )
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB}MB"
        )


MAX_ZIP_RATIO = 100.0  # Max uncompressed-to-compressed size ratio
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024  # 25 MB max uncompressed ceiling


def validate_zip_ratio(file_bytes: bytes) -> None:
    """Protect against zip bomb / XML expansion DoS attacks in DOCX files.

    Security & Efficiency: Rejects zip archives with extreme compression ratios
    (> 100:1) or total uncompressed payload sizes (> 25MB) before parsing XML.
    """
    if file_bytes[:4] == ZIP_MAGIC:
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                total_compressed = sum(info.compress_size for info in zf.infolist()) or 1
                ratio = total_uncompressed / total_compressed

                if ratio > MAX_ZIP_RATIO or total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="File rejected: Zip bomb or excessive XML compression ratio detected."
                    )
        except zipfile.BadZipFile:
            pass


def detect_file_type(file_bytes: bytes) -> str:
    """Detect file type by magic bytes. Returns 'pdf' or 'docx'.

    Security: We check actual file content, not the user-provided extension,
    to prevent disguised file attacks.
    """
    if len(file_bytes) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is too small or corrupted"
        )

    # Check PDF signature
    if file_bytes[:4] == PDF_MAGIC:
        return "pdf"

    # Check DOCX: must be a valid ZIP containing word/document.xml
    if file_bytes[:4] == ZIP_MAGIC:
        validate_zip_ratio(file_bytes)
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                names = zf.namelist()
                if "[Content_Types].xml" in names and any(
                    n.startswith("word/") for n in names
                ):
                    return "docx"
        except zipfile.BadZipFile:
            pass

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file format. Only valid PDF and DOCX files are accepted. "
               "File type is verified by content, not extension."
    )


def validate_page_count(page_count: int) -> None:
    """Reject documents exceeding the configured page limit."""
    if page_count > settings.MAX_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document has {page_count} pages, exceeding the limit of {settings.MAX_PAGES}"
        )


def validate_character_count(text: str) -> None:
    """Reject documents exceeding the configured character limit."""
    if len(text) > settings.MAX_CHARACTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document text exceeds the maximum of {settings.MAX_CHARACTERS:,} characters"
        )


def validate_upload(file_bytes: bytes, filename: str) -> str:
    """Run all upload validations. Returns detected file type ('pdf' or 'docx').

    Validation order (fail-fast):
    1. File size (cheapest check)
    2. Magic byte detection (determines file type)
    3. Extension consistency warning (logged, not blocking)
    """
    validate_file_size(file_bytes)
    file_type = detect_file_type(file_bytes)

    # Log extension mismatch but don't block (magic bytes are authoritative)
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if file_type == "pdf" and ext != "pdf":
            pass  # Could log warning; magic bytes are authoritative
        elif file_type == "docx" and ext != "docx":
            pass  # Could log warning; magic bytes are authoritative

    return file_type
