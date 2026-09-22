"""Clause extraction and document classification prompts.

Extracts distinct clauses from page-aware document text, preserving
verbatim text for verifiability. Also classifies the document type.

Efficiency: Pages are processed in batches of ~5 to balance extraction
quality against API call count. One batch = one LLM call.
"""

import logging

from backend.models.schemas import (
    ClassificationResult,
    Clause,
    DocumentType,
    ExtractionResult,
    PageText,
)
from backend.prompts.gemini_client import call_gemini_structured
from backend.security.prompt_guard import get_data_boundary_instruction, wrap_document_content

logger = logging.getLogger(__name__)

# Default adaptive batching target limits
TARGET_CHARS_PER_BATCH = 8000
MAX_PAGES_PER_BATCH = 10


def create_adaptive_batches(
    pages: list[PageText], target_chars: int = TARGET_CHARS_PER_BATCH, max_pages: int = MAX_PAGES_PER_BATCH
) -> list[list[PageText]]:
    """Group pages dynamically by character count and max page limit.

    Target ~8,000 characters per batch or max 10 pages per batch to balance
    extraction quality against LLM API calls.
    """
    if not pages:
        return []

    batches: list[list[PageText]] = []
    current_batch: list[PageText] = []
    current_chars = 0

    for page in pages:
        page_len = len(page.text)
        if current_batch and (current_chars + page_len > target_chars or len(current_batch) >= max_pages):
            batches.append(current_batch)
            current_batch = [page]
            current_chars = page_len
        else:
            current_batch.append(page)
            current_chars += page_len

    if current_batch:
        batches.append(current_batch)

    return batches


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

    Processes pages in adaptive batches to balance extraction quality against API calls.
    Each clause preserves verbatim text (no paraphrasing) with page reference.
    """
    all_clauses: list[Clause] = []
    clause_counter = 0

    batches = create_adaptive_batches(pages)
    for batch in batches:

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
