"""
MODULE: Q&A and scenario analysis FastAPI chat router.

@level-one-validation: Endpoints correctly retrieve session state, refresh last_accessed timestamps, and pass top-k clauses to legal_analyzer. Solid integration tested in test_api.py and test_e2e_integration.py.

#Scope-Of-Improvement: Add stream response option for long scenario analyses to improve perceived client UI latency.
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.limiter import limiter
from backend.models.schemas import AskRequest, QAResponse, ScenarioRequest, ScenarioResponse
from backend.services.legal_analyzer import (
    analyze_scenario_for_document,
    ask_question_about_document,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# #What: Safely fetches document session from app.state and updates last_accessed timestamp
def _get_session(session_id: str, request: Request):
    """Retrieve session or raise 404."""
    if not hasattr(request.app.state, "sessions"):
        request.app.state.sessions = {}
    sessions = request.app.state.sessions
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Please upload a document first."
        )
    session.last_accessed = time.time()
    return session


# #What: Safely fetches TF-IDF clause retriever instance for specified session
def _get_retriever(session_id: str, request: Request):
    """Retrieve the clause retriever for a session."""
    if not hasattr(request.app.state, "retrievers"):
        request.app.state.retrievers = {}
    retrievers = request.app.state.retrievers
    retriever = retrievers.get(session_id)
    if not retriever:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session retriever not found. Please upload a document first."
        )
    return retriever


# #Business-Intent: Implements evidence-grounded Q&A satisfying the challenge requirement for question answering with strict certainty distinction.
@router.post("/{session_id}/ask", response_model=QAResponse)
@limiter.limit("30/minute")
async def ask_question(session_id: str, body: AskRequest, request: Request):
    """Ask a question about the uploaded document.

    Uses retrieval-first approach: only top-k relevant clauses are sent
    to the LLM, never the full document. Response includes citations
    and three-way certainty distinction.
    """
    session = _get_session(session_id, request)
    retriever = _get_retriever(session_id, request)

    response = await ask_question_about_document(
        question=body.question,
        clauses=session.clauses,
        retriever=retriever,
    )

    # Accumulate lawyer questions and unclear items for the prep brief
    if response.lawyer_question:
        session.lawyer_questions.append(response.lawyer_question)
    if response.not_established:
        session.unclear_items.append(response.not_established)

    logger.info(f"QA: session={session_id}, certainty={response.certainty}, sources={len(response.sources)}")
    return response


# #Business-Intent: Implements Scenario Simulator allowing users to evaluate hypothetical real-world outcomes without receiving legal advice.
@router.post("/{session_id}/scenario", response_model=ScenarioResponse)
@limiter.limit("20/minute")
async def analyze_scenario(session_id: str, body: ScenarioRequest, request: Request):
    """Analyze a hypothetical scenario against the document.

    Uses cross-category retrieval to find relevant clauses from different
    parts of the document for comprehensive scenario analysis.
    """
    session = _get_session(session_id, request)
    retriever = _get_retriever(session_id, request)

    response = await analyze_scenario_for_document(
        scenario=body.scenario,
        clauses=session.clauses,
        retriever=retriever,
    )

    # Accumulate for prep brief
    if response.lawyer_question:
        session.lawyer_questions.append(response.lawyer_question)
    if response.unclear:
        session.unclear_items.append(response.unclear)

    logger.info(f"Scenario: session={session_id}, relevant_clauses={len(response.relevant_clauses)}")
    return response
