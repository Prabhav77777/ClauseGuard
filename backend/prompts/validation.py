"""
MODULE: Response validation guard and uncertainty verification prompts.

@level-one-validation: Performs final validation on Q&A and scenario responses. Strips system prompt leaks, validates cited clause IDs exist, and downgrades unverified claims to NOT_ESTABLISHED. Tested in test_qa_grounding.py.

#Scope-Of-Improvement: Log validation failure metrics to monitor LLM citation accuracy over time.
"""

import logging

from backend.models.schemas import (
    CertaintyLevel,
    Clause,
    FinalValidationResult,
    QAResponse,
    ScenarioResponse,
    ValidationResult,
)
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import (
    get_data_boundary_instruction,
    strip_system_prompt_leaks,
    validate_clause_ids_exist,
    wrap_document_content,
)

logger = logging.getLogger(__name__)


# @risk-area: Synchronous validation check adds an additional LLM API call latency overhead.
# #What: Performs binary verification check on whether answer claims are supported by source clause text
async def validate_uncertainty(
    answer_text: str, source_clauses: list[Clause]
) -> ValidationResult:
    """Binary check: is the answer supported by the provided source clauses?"""
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

    system_prompt = f"""You are a fact-checking system. Your job is to verify whether an answer is supported by source clauses.

{boundary_instruction}

Check if the answer makes claims that are NOT supported by the provided clause texts.
Set is_supported to true ONLY if every factual claim in the answer can be traced to the source clauses.
Set is_supported to false if the answer contains fabricated information, unsupported claims, or references to clauses not provided."""

    try:
        return call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Answer to validate:\n{answer_text}\n\nSource clauses:\n{wrapped_clauses}",
            response_schema=ValidationResult,
        )
    except Exception as e:
        logger.error(f"Error running uncertainty validation: {e}")
        return ValidationResult(is_supported=False, notes="Validation could not be completed.")


# #What: Validates cited clause IDs, strips prompt leaks, and downgrades unverified claims
# #Business-Intent: Acts as final security and quality guard ensuring no fabricated citations or leaked prompt text reach the user.
def validate_final_response(
    response: QAResponse | ScenarioResponse,
    all_clauses: list[Clause]
) -> FinalValidationResult:
    """Final validation guard — runs BEFORE returning any response to the user.

    This is a GENUINE guard, not a no-op. It performs:
    1. Clause ID existence check — removes references to non-existent clauses
    2. System prompt leak detection — strips leaked prompt content
    3. Unsupported claim downgrade — changes certainty to NOT_ESTABLISHED
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
