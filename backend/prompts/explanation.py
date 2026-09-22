"""Plain-language clause explanation prompt.

Generates simple, jargon-free explanations for legal clauses.
Processes clauses in batches to reduce API call count.

Efficiency: Clauses are batched (up to 10 per call) since explanations
are short outputs. This reduces API calls from N to ceil(N/10).
"""

import anthropic
import logging
from backend.config import settings
from backend.models.schemas import (
    Clause, PlainExplanationResult, BatchExplanationResult
)
from backend.security.prompt_guard import wrap_document_content, get_data_boundary_instruction

logger = logging.getLogger(__name__)

# Batch size for explanation generation
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
        
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=4096,
            system=f"""You are a legal document simplifier. Explain legal clauses in plain, everyday English.

{boundary_instruction}

Rules:
1. Use simple, jargon-free language that a non-lawyer can understand.
2. Do NOT add any facts, obligations, rights, or details that are not in the clause text.
3. Do NOT give legal advice or opinions about enforceability.
4. Do NOT mention risk levels or scores.
5. Focus on what the clause means for the person reading it.
6. Keep explanations concise — 2-4 sentences per clause.
7. Provide an explanation for EVERY clause in the input.""",
            tools=[{
                "name": "explain",
                "description": "Output plain-language explanations for clauses.",
                "input_schema": BatchExplanationResult.model_json_schema()
            }],
            tool_choice={"type": "tool", "name": "explain"},
            messages=[{"role": "user", "content": f"Explain each of these clauses in plain English:\n{wrapped_text}"}]
        )
        
        for block in response.content:
            if block.type == "tool_use":
                result = BatchExplanationResult(**block.input)
                all_explanations.extend(result.explanations)
    
    logger.info(f"Generated {len(all_explanations)} explanations")
    return all_explanations
