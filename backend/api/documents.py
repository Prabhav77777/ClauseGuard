"""Document upload and management endpoints.

Handles file upload with validation, triggers the full processing pipeline
(parse -> extract -> categorize -> explain), and provides access to
processed clause data.
"""

import hashlib
import logging
import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from backend.core.limiter import limiter
from backend.models.schemas import Clause, DocumentSession, UploadResponse
from backend.security.validation import validate_upload
from backend.services.brief_generator import generate_brief
from backend.services.clause_extractor import process_document
from backend.services.retriever import ClauseRetriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Efficiency: In-memory content hash cache to avoid re-parsing & re-processing identical files
_DOCUMENT_CONTENT_CACHE: dict[str, dict[str, Any]] = {}


def _get_sessions(request: Request) -> dict[str, Any]:
    """Access the in-memory session store from app state safely."""
    if not hasattr(request.app.state, "sessions"):
        request.app.state.sessions = {}
    sessions_dict: dict[str, Any] = request.app.state.sessions
    return sessions_dict


def _get_retrievers(request: Request) -> dict[str, Any]:
    """Access the retriever cache from app state safely."""
    if not hasattr(request.app.state, "retrievers"):
        request.app.state.retrievers = {}
    retrievers_dict: dict[str, Any] = request.app.state.retrievers
    return retrievers_dict


@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """Upload and process a legal document.

    Validates the file (magic bytes, size), then runs the full pipeline:
    parse -> classify -> extract -> categorize -> explain.

    Returns a session ID and the full list of processed clauses.
    """
    try:
        # Read file bytes with size check
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty"
            )

        # Validate file type and size (security: magic bytes, not extension)
        file_type = validate_upload(file_bytes, file.filename or "")

        # Efficiency: Compute SHA-256 hash to check if this exact file was already processed
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        if content_hash in _DOCUMENT_CONTENT_CACHE:
            logger.info(f"Efficiency: Content-hash cache hit for SHA256 {content_hash[:8]}")
            cached = _DOCUMENT_CONTENT_CACHE[content_hash]
            pages = cached["pages"]
            clauses = cached["clauses"]
            classification = cached["classification"]
            retriever = cached["retriever"]
        else:
            # Run the full processing pipeline
            pages, clauses, classification = await process_document(file_bytes, file_type)
            retriever = ClauseRetriever(clauses)
            _DOCUMENT_CONTENT_CACHE[content_hash] = {
                "pages": pages,
                "clauses": clauses,
                "classification": classification,
                "retriever": retriever,
            }

        # Create session (always issue a unique session_id for independent session lifecycle)
        session_id = str(uuid.uuid4())
        session = DocumentSession(
            session_id=session_id,
            filename=file.filename or "unknown",
            doc_type=classification.doc_type,
            clauses=clauses,
            raw_pages=pages,
        )

        # Store session and build retriever
        sessions = _get_sessions(request)
        sessions[session_id] = session

        retrievers = _get_retrievers(request)
        retrievers[session_id] = retriever

        logger.info(f"Document uploaded: session={session_id}, type={classification.doc_type}, clauses={len(clauses)}")

        return UploadResponse(
            session_id=session_id,
            filename=file.filename or "unknown",
            doc_type=classification.doc_type,
            total_pages=len(pages),
            total_clauses=len(clauses),
            clauses=clauses,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document upload: {e}", exc_info=True)
        err_str = str(e)
        if "api_key" in err_str.lower() or "authentication" in err_str.lower() or "gemini" in err_str.lower() or "google" in err_str.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gemini API key is invalid or missing. Please set GEMINI_API_KEY in your .env file."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while processing the document."
        )
    finally:
        await file.close()


@router.get("/{session_id}/clauses", response_model=list[Clause])
async def get_clauses(session_id: str, request: Request):
    """Get all clauses for a session."""
    sessions = _get_sessions(request)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Please upload a document first."
        )
    return session.clauses


@router.get("/{session_id}/clauses/{clause_id}", response_model=Clause)
async def get_clause(session_id: str, clause_id: str, request: Request):
    """Get a specific clause by ID."""
    sessions = _get_sessions(request)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    for clause in session.clauses:
        if clause.id == clause_id:
            return clause

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Clause '{clause_id}' not found"
    )

@router.get("/{session_id}/brief")
async def get_lawyer_brief(session_id: str, request: Request):
    """Generate and return the Lawyer Prep Brief as markdown."""
    sessions = _get_sessions(request)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    brief_md = generate_brief(session)
    return PlainTextResponse(content=brief_md, media_type="text/markdown")
