"""
MODULE: Two-document comparison prompt orchestration.

@level-one-validation: Compares clause sets between two document versions and outputs structured ComparisonResult. Solid prompt guard isolation. Tested in test_comparison.py.

#Scope-Of-Improvement: Pre-align matching clauses using fuzzy string matching before calling LLM to reduce prompt context size.
"""

import logging

from backend.models.schemas import Clause, ComparisonResult
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import get_data_boundary_instruction, wrap_document_content

logger = logging.getLogger(__name__)


# #Uncertain: LLM diff alignment may hallucinate non-existent diffs if clause order in Doc2 changes radically relative to Doc1.
# #Business-Intent: Implements contract comparison feature classifying diffs as Added/Removed/Modified with cosmetic vs substantive materiality.
async def compare_documents(
    clauses_doc1: list[Clause], clauses_doc2: list[Clause]
) -> ComparisonResult:
    """Compare clauses between two documents.

    Identifies added, removed, and modified clauses with materiality
    classification and justification.
    """
    doc1_text = "\n".join(
        f"[DOC1 - {c.id}] {c.section}: {c.text}" for c in clauses_doc1
    )
    doc2_text = "\n".join(
        f"[DOC2 - {c.id}] {c.section}: {c.text}" for c in clauses_doc2
    )

    combined = f"DOCUMENT 1 CLAUSES:\n{doc1_text}\n\nDOCUMENT 2 CLAUSES:\n{doc2_text}"
    wrapped_text, nonce = wrap_document_content(combined)
    boundary_instruction = get_data_boundary_instruction(nonce)

    system_prompt = f"""You are a legal document comparison system. Compare clauses between two versions of a document.

{boundary_instruction}

For each difference found:
1. 'status': 'Added' (in doc2 only), 'Removed' (in doc1 only), or 'Modified' (changed between versions)
2. 'old': The original text from doc1 (null if Added)
3. 'new': The new text from doc2 (null if Removed)
4. 'materiality': 'cosmetic' (formatting, minor wording) or 'substantive' (changes meaning, obligations, rights)
5. 'reason': A clear justification for the materiality classification

Rules:
1. Match clauses by their section/topic, not by position.
2. Only report actual differences, not identical clauses.
3. Materiality MUST include a stated justification.
4. Be precise about what changed and why it matters."""

    try:
        result = call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Compare these two documents:\n{wrapped_text}",
            response_schema=ComparisonResult,
        )
        logger.info(f"Comparison found {len(result.items)} differences")
        return result
    except Exception as e:
        logger.error(f"Error comparing documents with Gemini: {e}")
        return ComparisonResult(items=[])
