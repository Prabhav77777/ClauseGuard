"""Clause categorization prompt.

Assigns each clause to a category from the fixed taxonomy. Processes
all clauses in a single batch to minimize API calls.

Efficiency: All clauses are sent in one LLM call since we only need
category labels (small output), not full analysis.
"""

import anthropic
import logging
from backend.config import settings
from backend.models.schemas import (
    Clause, ClauseCategory, CategorizationResult, BatchCategorizationResult
)
from backend.security.prompt_guard import wrap_document_content, get_data_boundary_instruction

logger = logging.getLogger(__name__)


async def categorize_clauses(clauses: list[Clause]) -> list[CategorizationResult]:
    """Assign categories to all clauses from the fixed taxonomy.
    
    Sends all clauses in a single LLM call for efficiency.
    Categories must be from the ClauseCategory enum only.
    """
    if not clauses:
        return []
    
    # Format clauses for the LLM
    clauses_text = ""
    for clause in clauses:
        clauses_text += f"\nID: {clause.id}\nSection: {clause.section}\nText: {clause.text}\n---\n"
    
    wrapped_text, nonce = wrap_document_content(clauses_text)
    boundary_instruction = get_data_boundary_instruction(nonce)
    
    categories_list = ", ".join([c.value for c in ClauseCategory])
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2048,
        system=f"""You are a legal clause categorization system.

{boundary_instruction}

Categorize each clause into exactly ONE of these categories: {categories_list}

Rules:
1. You MUST select from the provided category list only.
2. If a clause doesn't fit well, use 'general'.
3. Categorize based on the primary purpose of the clause.
4. Return a categorization for EVERY clause provided.""",
        tools=[{
            "name": "categorize",
            "description": "Output clause categorizations.",
            "input_schema": BatchCategorizationResult.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "categorize"},
        messages=[{"role": "user", "content": f"Categorize each of these clauses:\n{wrapped_text}"}]
    )
    
    for block in response.content:
        if block.type == "tool_use":
            result = BatchCategorizationResult(**block.input)
            logger.info(f"Categorized {len(result.categorizations)} clauses")
            return result.categorizations
    
    # Fallback: assign 'general' to all if LLM fails
    return [
        CategorizationResult(clause_id=c.id, category=ClauseCategory.GENERAL)
        for c in clauses
    ]
