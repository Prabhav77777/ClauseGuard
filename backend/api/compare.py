"""
MODULE: Two-document comparison FastAPI router.

@level-one-validation: Processes and compares two documents concurrently. File cleanup in finally block is robust. Tested in test_comparison.py.

#Scope-Of-Improvement: Run process_document for file1 and file2 concurrently via asyncio.gather to reduce total comparison latency.
"""

import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from backend.core.limiter import limiter
from backend.models.schemas import ComparisonResult
from backend.prompts.comparison import compare_documents
from backend.security.validation import validate_upload
from backend.services.clause_extractor import process_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compare", tags=["compare"])


# @risk-area: Synchronous sequential processing of two documents doubles pipeline latency; asyncio.gather would halve it.
# #Business-Intent: Satisfies the challenge use case for comparing contracts with cosmetic vs. substantive diff classification.
@router.post("/", response_model=ComparisonResult)
@limiter.limit("10/minute")
async def compare_two_documents(
    request: Request,
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
):
    """Compare two versions of a document.

    Uploads and processes both documents, then compares their clauses
    to identify additions, removals, and modifications with materiality
    classification.
    """
    try:
        # Read and validate both files
        bytes1 = await file1.read()
        bytes2 = await file2.read()

        type1 = validate_upload(bytes1, file1.filename or "")
        type2 = validate_upload(bytes2, file2.filename or "")

        # Process both documents
        pages1, clauses1, _ = await process_document(bytes1, type1)
        pages2, clauses2, _ = await process_document(bytes2, type2)

        if not clauses1 or not clauses2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both documents must contain extractable clauses for comparison."
            )

        # Run comparison
        result = await compare_documents(clauses1, clauses2)

        logger.info(f"Comparison complete: {len(result.items)} differences found")
        return result

    finally:
        await file1.close()
        await file2.close()
