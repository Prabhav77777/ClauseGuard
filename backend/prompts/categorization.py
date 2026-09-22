"""Clause categorization prompt.

Assigns each clause to a category from the fixed taxonomy. Processes
all clauses in a single batch to minimize API calls.
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


async def categorize_clauses(clauses: list[Clause]) -> list[CategorizationResult]:
    """Assign categories to all clauses from the fixed taxonomy.

    Sends all clauses in a single Gemini API call for efficiency.
    Categories must be from the ClauseCategory enum only.
    """
    if not clauses:
        return []

    clauses_text = ""
    for clause in clauses:
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
        result = call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Categorize each of these clauses:\n{wrapped_text}",
            response_schema=BatchCategorizationResult,
        )
        logger.info(f"Categorized {len(result.categorizations)} clauses")
        return result.categorizations
    except Exception as e:
        logger.error(f"Error categorizing clauses: {e}")
        return [
            CategorizationResult(clause_id=c.id, category=ClauseCategory.GENERAL)
            for c in clauses
        ]
