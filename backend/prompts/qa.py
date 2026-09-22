"""Evidence-grounded Q&A prompt.

Answers user questions using ONLY retrieved clauses (never the full document).
Every answer carries a citation and a three-way certainty distinction:
- STATED: What the document explicitly says
- INTERPRETED: Reasonable inference
- NOT_ESTABLISHED: Cannot be determined from the document
"""

import logging

from backend.models.schemas import CertaintyLevel, Clause, QAResponse
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import get_data_boundary_instruction, wrap_document_content

logger = logging.getLogger(__name__)


async def answer_question(question: str, retrieved_clauses: list[Clause]) -> QAResponse:
    """Answer a question using only the retrieved clauses.

    The full document is NEVER sent — only top-k relevant clauses from
    the retriever.
    """
    if not retrieved_clauses:
        return QAResponse(
            answer="I could not find any relevant clauses in the document to answer this question.",
            sources=[],
            certainty=CertaintyLevel.NOT_ESTABLISHED,
            stated="No relevant clauses were found in the document for this topic.",
            interpreted="",
            not_established="This topic does not appear to be covered by any clause in the document.",
            lawyer_question="You may want to ask your lawyer whether this topic should be addressed in the agreement."
        )

    clauses_text = ""
    clause_ids = []
    for clause in retrieved_clauses:
        clauses_text += f"\nClause ID: {clause.id}\nSection: {clause.section}\nPage: {clause.page}\nText: {clause.text}\n---\n"
        clause_ids.append(clause.id)

    wrapped_text, nonce = wrap_document_content(clauses_text)
    boundary_instruction = get_data_boundary_instruction(nonce)
    available_ids = ", ".join(clause_ids)

    system_prompt = f"""You are ClauseGuard, a legal document analysis assistant. Answer questions about legal documents based ONLY on the provided clause excerpts.

{boundary_instruction}

You are NOT a lawyer. You do NOT provide legal advice. You NEVER fabricate clauses, dates, penalties, rights, obligations, or citations.

For every answer, you MUST provide a three-way distinction:
1. 'stated': What the document EXPLICITLY says (quote or closely paraphrase the relevant text)
2. 'interpreted': What can be REASONABLY INFERRED (label this clearly as interpretation)
3. 'not_established': What CANNOT be determined from the provided clauses

Rules:
1. ONLY cite clause IDs from this list: {available_ids}. Never invent clause IDs.
2. If the question cannot be answered from the provided clauses, set certainty to 'not_established' and explain what's missing.
3. Never make up information. If something is unclear, say so explicitly.
4. Suggest a question the user could ask their lawyer about unclear points.
5. Never claim to be a lawyer or give legal conclusions about enforceability."""

    try:
        result = call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Question: {question}\n\nRelevant clauses from the document:\n{wrapped_text}",
            response_schema=QAResponse,
        )
        logger.info(f"QA response with {len(result.sources)} citations, certainty: {result.certainty}")
        return result
    except Exception as e:
        logger.error(f"Error answering question with Gemini: {e}")
        return QAResponse(
            answer="I was unable to process your question. Please try rephrasing.",
            sources=[],
            certainty=CertaintyLevel.NOT_ESTABLISHED,
            stated="",
            interpreted="",
            not_established="The system was unable to analyze the relevant clauses for this question.",
            lawyer_question=None
        )
