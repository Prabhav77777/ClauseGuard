"""Plain-language clause explanation prompt.

Generates simple, jargon-free explanations for legal clauses.
Processes clauses in batches to reduce API call count.
"""

import logging

from backend.models.schemas import BatchExplanationResult, Clause, PlainExplanationResult
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import get_data_boundary_instruction, wrap_document_content

logger = logging.getLogger(__name__)

CLAUSES_PER_BATCH = 10


async def explain_clauses(clauses: list[Clause]) -> list[PlainExplanationResult]:
    """Generate plain-English explanations for clauses.

    Processes clauses in batches of 10 to reduce API calls.
    Explanations must not add facts absent from the clause text.
    """
    if not clauses:
        return []

    all_explanations: list[PlainExplanationResult] = []

    for batch_start in range(0, len(clauses), CLAUSES_PER_BATCH):
        batch = clauses[batch_start:batch_start + CLAUSES_PER_BATCH]

        clauses_text = ""
        for clause in batch:
            clauses_text += f"\nID: {clause.id}\nSection: {clause.section}\nText: {clause.text}\n---\n"

        wrapped_text, nonce = wrap_document_content(clauses_text)
        boundary_instruction = get_data_boundary_instruction(nonce)

        system_prompt = f"""You are a legal document simplifier. Explain legal clauses in plain, everyday English.

{boundary_instruction}

Rules:
1. Use simple, jargon-free language that a non-lawyer can understand.
2. Do NOT add any facts, obligations, rights, or details that are not in the clause text.
3. Do NOT give legal advice or opinions about enforceability.
4. Do NOT mention risk levels or scores.
5. Focus on what the clause means for the person reading it.
6. Keep explanations concise — 2-4 sentences per clause.
7. Provide an explanation for EVERY clause in the input."""

        try:
            result = call_gemini_structured(
                system_instruction=system_prompt,
                user_content=f"Explain each of these clauses in plain English:\n{wrapped_text}",
                response_schema=BatchExplanationResult,
            )
            all_explanations.extend(result.explanations)
        except Exception as e:
            logger.error(f"Error explaining clauses batch: {e}")

    logger.info(f"Generated {len(all_explanations)} explanations")
    return all_explanations
