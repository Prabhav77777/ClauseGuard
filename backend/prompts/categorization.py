"""
MODULE: Clause categorization prompt orchestration.

@level-one-validation: Batch categorizes clauses using structured JSON response schema. Fallback assigns GENERAL category on LLM failure. Tested in test_extraction.py.

#Scope-Of-Improvement: Split very large clause sets (>100 clauses) into multiple sub-batches to prevent hitting prompt output token limits.
"""

import logging

from backend.models.schemas import (
    BatchCategorizationResult,
    CategorizationResult,
    Clause,
    ClauseCategory,
)
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import get_data_boundary_instruction, wrap_document_content

logger = logging.getLogger(__name__)


# #Business-Intent: Fast deterministic clause categorization by section title header matching.
def categorize_clause_deterministic(section: str) -> ClauseCategory | None:
    """Attempt fast deterministic categorization based on explicit section title keywords.

    Returns ClauseCategory if section title contains explicit canonical keywords, or None if ambiguous.
    """
    if not section:
        return None

    sec_lower = section.lower()

    canonical_title_map = [
        (ClauseCategory.COMPENSATION, ["compensation", "salary", "base pay", "remuneration"]),
        (ClauseCategory.TERMINATION, ["termination", "cancellation"]),
        (ClauseCategory.NOTICE_PERIOD, ["notice period"]),
        (ClauseCategory.PROBATION, ["probation", "probationary"]),
        (ClauseCategory.NON_COMPETE, ["non-compete", "non compete", "covenant not to compete"]),
        (ClauseCategory.CONFIDENTIALITY, ["confidentiality", "confidential information", "non-disclosure"]),
        (ClauseCategory.LIABILITY, ["limitation of liability", "liability"]),
        (ClauseCategory.INTELLECTUAL_PROPERTY, ["intellectual property", "ip rights", "inventions"]),
        (ClauseCategory.DISPUTE_RESOLUTION, ["dispute resolution", "arbitration"]),
        (ClauseCategory.GOVERNING_LAW, ["governing law", "jurisdiction"]),
        (ClauseCategory.BENEFITS, ["employee benefits", "fringe benefits"]),
        (ClauseCategory.INDEMNIFICATION, ["indemnification", "indemnity"]),
    ]

    for category, keywords in canonical_title_map:
        for kw in keywords:
            if kw in sec_lower:
                return category

    return None


# #Uncertain: Single-batch LLM categorization may hit output token limits if document contains >100 clauses.
# #Business-Intent: Categorizes clauses into fixed 15-category taxonomy using hybrid fast-path classification.
async def categorize_clauses(clauses: list[Clause]) -> list[CategorizationResult]:
    """Assign categories to all clauses from the fixed taxonomy.

    Efficiency: Uses hybrid fast-path classification on explicit section titles first.
    Sends only uncategorized clauses to Gemini LLM in a single API call.
    """
    if not clauses:
        return []

    results: list[CategorizationResult] = []
    unmatched_clauses: list[Clause] = []

    # Step 1: Fast deterministic title categorization
    for clause in clauses:
        det_cat = categorize_clause_deterministic(clause.section)
        if det_cat is not None:
            results.append(CategorizationResult(clause_id=clause.id, category=det_cat))
        else:
            unmatched_clauses.append(clause)

    if not unmatched_clauses:
        logger.info(f"Efficiency: 100% of {len(clauses)} clauses categorized deterministically via section headers")
        return results

    # Step 2: Send remaining unmatched clauses to Gemini LLM
    clauses_text = ""
    for clause in unmatched_clauses:
        clauses_text += f"\nID: {clause.id}\nSection: {clause.section}\nText: {clause.text}\n---\n"

    wrapped_text, nonce = wrap_document_content(clauses_text)
    boundary_instruction = get_data_boundary_instruction(nonce)

    categories_list = ", ".join([c.value for c in ClauseCategory])

    system_prompt = f"""You are a legal clause categorization system.

{boundary_instruction}

Categorize each clause into exactly ONE of these categories: {categories_list}

Rules:
1. You MUST select from the provided category list only.
2. If a clause doesn't fit well, use 'general'.
3. Categorize based on the primary purpose of the clause.
4. Return a categorization for EVERY clause provided."""

    try:
        llm_result = call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Categorize each of these clauses:\n{wrapped_text}",
            response_schema=BatchCategorizationResult,
        )
        results.extend(llm_result.categorizations)
        logger.info(f"Categorized {len(clauses)} total clauses ({len(clauses) - len(unmatched_clauses)} deterministic, {len(unmatched_clauses)} via LLM)")
        return results
    except Exception as e:
        logger.error(f"Error categorizing remaining clauses: {e}")
        for c in unmatched_clauses:
            results.append(CategorizationResult(clause_id=c.id, category=ClauseCategory.GENERAL))
        return results
