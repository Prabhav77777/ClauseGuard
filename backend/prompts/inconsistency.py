"""
MODULE: Cross-clause inconsistency detection using Gemini structured output.

@level-one-validation: Scans document clauses for contradictory provisions. Uses prompt boundary nonces. Tested in test_inconsistency.py.

#Scope-Of-Improvement: Log inconsistency detection confidence metrics for audit tracing.
"""

import logging

from backend.models.schemas import Clause, InconsistencyReport, InconsistencyResult
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import (
    get_data_boundary_instruction,
    wrap_document_content,
)

logger = logging.getLogger(__name__)


# #Business-Intent: Fulfills challenge requirement for cross-clause inconsistency detection without guessing controlling provisions.
async def detect_inconsistencies(clauses: list[Clause]) -> list[InconsistencyResult]:
    """Analyze a document's clauses to identify contradictory or conflicting provisions.

    Args:
        clauses: Extracted clauses from a single document.

    Returns:
        List of InconsistencyResult objects detailing identified clause pairs.
    """
    if not clauses:
        return []

    # Format clauses into structured text block
    clause_lines = []
    for c in clauses:
        clause_lines.append(f"[{c.id}] Section: {c.section} (Page {c.page})\nContent: {c.text}\n")
    document_text = "\n".join(clause_lines)

    # Wrap in prompt injection data delimiters
    wrapped_text, nonce = wrap_document_content(document_text)
    boundary_instruction = get_data_boundary_instruction(nonce)

    system_instruction = (
        f"You are ClauseGuard's Inconsistency Detector. Your task is to analyze the provided legal document "
        f"clauses to find conflicting, contradictory, or inconsistent terms between pairs of clauses.\n\n"
        f"{boundary_instruction}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Examine the clauses for contradictory terms (e.g. differing notice periods like 30 days vs 60 days, "
        f"conflicting termination requirements, contradictory IP ownership claims, or conflicting liability caps).\n"
        f"2. For each inconsistency found, return a JSON object with 'clause_ids' (the exact list of IDs of "
        f"the inconsistent clauses, e.g. ['clause_002', 'clause_014']) and 'description'.\n"
        f"3. CRITICAL MANDATE: You MUST NEVER attempt to resolve which provision controls or declare a winning clause. "
        f"You must explicitly state in the description what terms conflict and note that the document leaves the controlling provision undetermined.\n"
        f"4. If no inconsistencies exist between clauses, return an empty list of inconsistencies."
    )

    user_content = f"Analyze the following document clauses for internal inconsistencies:\n\n{wrapped_text}"

    try:
        report = call_gemini_structured(
            system_instruction=system_instruction,
            user_content=user_content,
            response_schema=InconsistencyReport,
            temperature=0.1,
        )
        return report.inconsistencies
    except Exception as e:
        logger.error(f"Error during inconsistency detection: {e}", exc_info=True)
        return []
