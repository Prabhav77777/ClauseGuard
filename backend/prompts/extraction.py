"""Clause extraction and document classification prompts.

Extracts distinct clauses from page-aware document text, preserving
verbatim text for verifiability. Also classifies the document type.

Efficiency: Pages are processed in batches of ~5 to balance extraction
quality against API call count. One batch = one LLM call.
"""

import logging
from backend.models.schemas import (
    PageText, Clause, ExtractionResult, ClassificationResult, DocumentType
)
from backend.security.prompt_guard import wrap_document_content, get_data_boundary_instruction
from backend.prompts.gemini_client import call_gemini_structured

logger = logging.getLogger(__name__)

# Batch size for page processing — balances quality vs. API call count
PAGES_PER_BATCH = 5


async def classify_document(pages: list[PageText]) -> ClassificationResult:
    """Classify the document type from sampled text.
    
    Uses the first few pages to determine document type (employment agreement,
    lease, NDA, etc.). Selects from a fixed enum or 'unknown'.
    """
    sample_text = "\n\n".join(p.text for p in pages[:2])
    wrapped_text, nonce = wrap_document_content(sample_text)
    boundary_instruction = get_data_boundary_instruction(nonce)
    
    system_prompt = f"""You are a document classification system. Your task is to identify the type of legal document.

{boundary_instruction}

Classify the document as one of: employment_agreement, lease_agreement, service_agreement, nda, partnership_agreement, unknown.
You must select from this exact list. If uncertain, choose 'unknown'."""

    try:
        return call_gemini_structured(
            system_instruction=system_prompt,
            user_content=f"Classify this document:\n{wrapped_text}",
            response_schema=ClassificationResult,
        )
    except Exception as e:
        logger.error(f"Error classifying document: {e}")
        return ClassificationResult(doc_type=DocumentType.UNKNOWN, confidence=0.0)


async def extract_clauses_from_pages(pages: list[PageText]) -> list[Clause]:
    """Extract distinct clauses from document pages.
    
    Processes pages in batches to balance extraction quality against API calls.
    Each clause preserves verbatim text (no paraphrasing) with page reference.
    """
    all_clauses: list[Clause] = []
    clause_counter = 0
    
    for batch_start in range(0, len(pages), PAGES_PER_BATCH):
        batch = pages[batch_start:batch_start + PAGES_PER_BATCH]
        
        batch_text = ""
        for page in batch:
            batch_text += f"\n--- PAGE {page.page_number} ---\n{page.text}\n"
        
        wrapped_text, nonce = wrap_document_content(batch_text)
        boundary_instruction = get_data_boundary_instruction(nonce)
        
        system_prompt = f"""You are a legal document clause extractor. Extract distinct clauses from the document text.

{boundary_instruction}

Rules:
1. Extract each distinct clause, provision, or section as a separate item.
2. The 'text' field MUST contain the EXACT verbatim text from the document — do NOT paraphrase.
3. The 'section' field should be the clause heading/title, or a descriptive label if none exists.
4. The 'page' field must be the page number where the clause appears (from the PAGE markers).
5. Assign sequential IDs starting from clause_{clause_counter:03d}.
6. Do not merge unrelated clauses. Do not split a single clause into multiple entries.
7. Include ALL substantive clauses — do not skip any."""

        try:
            result = call_gemini_structured(
                system_instruction=system_prompt,
                user_content=f"Extract all clauses from these pages. Start IDs from clause_{clause_counter:03d}.\n{wrapped_text}",
                response_schema=ExtractionResult,
            )
            all_clauses.extend(result.clauses)
            clause_counter = len(all_clauses)
        except Exception as e:
            logger.error(f"Error extracting clauses from page batch: {e}")

    # Re-number clauses sequentially to ensure consistency
    for i, clause in enumerate(all_clauses):
        clause.id = f"clause_{i:03d}"
    
    logger.info(f"Extracted {len(all_clauses)} clauses from {len(pages)} pages")
    return all_clauses
