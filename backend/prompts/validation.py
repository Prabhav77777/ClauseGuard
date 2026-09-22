"""Response validation prompts — uncertainty check and final guard.

This module implements two validation steps:
1. Uncertainty validation: Binary check on whether an answer is supported by sources
2. Final response validation: Comprehensive guard that downgrades unsupported claims

This is a GENUINE guard, not a no-op. It actively checks and corrects responses.
"""

import anthropic
import json
import logging
from backend.config import settings
from backend.models.schemas import (
    Clause, QAResponse, ScenarioResponse, ValidationResult,
    FinalValidationResult, CertaintyLevel
)
from backend.security.prompt_guard import (
    wrap_document_content, get_data_boundary_instruction,
    strip_system_prompt_leaks, validate_clause_ids_exist
)

logger = logging.getLogger(__name__)


async def validate_uncertainty(
    answer_text: str, source_clauses: list[Clause]
) -> ValidationResult:
    """Binary check: is the answer supported by the provided source clauses?
    
    This is the first validation gate. If the answer references facts
    not present in the source clauses, it flags them.
    """
    if not source_clauses:
        return ValidationResult(
            is_supported=False,
            notes="No source clauses provided — answer cannot be validated."
        )
    
    clauses_text = "\n".join(
        f"[{c.id}]: {c.text}" for c in source_clauses
    )
    wrapped_clauses, nonce = wrap_document_content(clauses_text)
    boundary_instruction = get_data_boundary_instruction(nonce)
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=512,
        system=f"""You are a fact-checking system. Your job is to verify whether an answer is supported by source clauses.

{boundary_instruction}

Check if the answer makes claims that are NOT supported by the provided clause texts.
Set is_supported to true ONLY if every factual claim in the answer can be traced to the source clauses.
Set is_supported to false if the answer contains fabricated information, unsupported claims, or references to clauses not provided.""",
        tools=[{
            "name": "validate",
            "description": "Output validation result.",
            "input_schema": ValidationResult.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "validate"},
        messages=[{
            "role": "user",
            "content": f"Answer to validate:\n{answer_text}\n\nSource clauses:\n{wrapped_clauses}"
        }]
    )
    
    for block in response.content:
        if block.type == "tool_use":
            return ValidationResult(**block.input)
    
    return ValidationResult(is_supported=False, notes="Validation could not be completed.")


def validate_final_response(
    response: QAResponse | ScenarioResponse,
    all_clauses: list[Clause]
) -> FinalValidationResult:
    """Final validation guard — runs BEFORE returning any response to the user.
    
    This is a GENUINE guard, not a no-op. It performs:
    1. Clause ID existence check — removes references to non-existent clauses
    2. System prompt leak detection — strips leaked prompt content
    3. Unsupported claim downgrade — changes certainty to NOT_ESTABLISHED
    
    Unsupported claims are DOWNGRADED to 'not established', never silently deleted.
    """
    valid_ids = {c.id for c in all_clauses}
    corrections_made = False
    
    if isinstance(response, QAResponse):
        # 1. Validate cited clause IDs exist
        valid_sources = validate_clause_ids_exist(response.sources, valid_ids)
        if len(valid_sources) != len(response.sources):
            logger.warning(
                f"Removed {len(response.sources) - len(valid_sources)} "
                f"non-existent clause IDs from response"
            )
            response.sources = valid_sources
            corrections_made = True
        
        # 2. If no valid sources remain, downgrade to NOT_ESTABLISHED
        if not response.sources and response.certainty != CertaintyLevel.NOT_ESTABLISHED:
            response.certainty = CertaintyLevel.NOT_ESTABLISHED
            response.not_established = (
                response.not_established or ""
            ) + " [Note: No valid source clauses could be verified for this answer.]"
            corrections_made = True
        
        # 3. Strip system prompt leaks from all text fields
        response.answer = strip_system_prompt_leaks(response.answer)
        response.stated = strip_system_prompt_leaks(response.stated)
        response.interpreted = strip_system_prompt_leaks(response.interpreted)
        response.not_established = strip_system_prompt_leaks(response.not_established)
        if response.lawyer_question:
            response.lawyer_question = strip_system_prompt_leaks(response.lawyer_question)
    
    elif isinstance(response, ScenarioResponse):
        # 1. Validate cited clause IDs
        valid_clauses = validate_clause_ids_exist(response.relevant_clauses, valid_ids)
        if len(valid_clauses) != len(response.relevant_clauses):
            response.relevant_clauses = valid_clauses
            corrections_made = True
        
        # 2. Strip system prompt leaks
        response.what_document_says = strip_system_prompt_leaks(response.what_document_says)
        response.potential_implication = strip_system_prompt_leaks(response.potential_implication)
        response.unclear = strip_system_prompt_leaks(response.unclear)
        response.lawyer_question = strip_system_prompt_leaks(response.lawyer_question)
    
    if corrections_made:
        return FinalValidationResult(
            passed=False,
            corrected_response=response.model_dump()
        )
    
    return FinalValidationResult(passed=True, corrected_response=None)
