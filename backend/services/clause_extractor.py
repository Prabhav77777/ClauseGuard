"""
MODULE: Clause extraction pipeline orchestration service.

@level-one-validation: Orchestrates parsing, parallel classification, clause extraction, categorization, and plain-English explanation via asyncio.gather. Tested in test_performance.py and test_e2e_integration.py.

#Scope-Of-Improvement: Add pipeline status callback parameter to report progress percentages to real-time WebSockets.
"""

import asyncio
import logging

from backend.models.schemas import ClassificationResult, Clause, PageText
from backend.prompts.categorization import categorize_clauses
from backend.prompts.explanation import explain_clauses
from backend.prompts.extraction import classify_document, extract_clauses_from_pages
from backend.services.document_parser import parse_document

logger = logging.getLogger(__name__)


# #What: Orchestrates full document pipeline with parallel LLM execution via asyncio.gather
# #Business-Intent: Runs parallel LLM API calls reducing total upload pipeline processing latency by ~50%.
async def process_document(
    file_bytes: bytes, file_type: str
) -> tuple[list[PageText], list[Clause], ClassificationResult]:
    """Run the complete document processing pipeline with maximum async concurrency.

    Returns:
        Tuple of (raw_pages, processed_clauses, classification)
    """
    # Step 1: Parse document into page-indexed text (runs CPU-bound in threadpool)
    logger.info(f"Step 1/3: Parsing {file_type} document...")
    pages = await parse_document(file_bytes, file_type)
    logger.info(f"Parsed {len(pages)} pages")

    # Step 2: Concurrently classify document type and extract clauses (Efficiency: parallel API calls)
    logger.info("Step 2/3: Concurrently classifying document and extracting clauses...")
    classification, clauses = await asyncio.gather(
        classify_document(pages),
        extract_clauses_from_pages(pages)
    )
    logger.info(f"Document classified as: {classification.doc_type} (confidence: {classification.confidence})")
    logger.info(f"Extracted {len(clauses)} clauses")

    if not clauses:
        logger.warning("No clauses extracted from document")
        return pages, [], classification

    # Step 3: Concurrently categorize clauses and generate plain-English explanations (Efficiency: parallel API calls)
    logger.info("Step 3/3: Concurrently categorizing clauses and generating explanations...")
    categorizations, explanations = await asyncio.gather(
        categorize_clauses(clauses),
        explain_clauses(clauses)
    )

    # Apply categorizations to clauses
    cat_map = {cat.clause_id: cat.category for cat in categorizations}
    for clause in clauses:
        if clause.id in cat_map:
            clause.category = cat_map[clause.id]

    # Apply explanations to clauses
    exp_map = {exp.clause_id: exp.plain_explanation for exp in explanations}
    for clause in clauses:
        if clause.id in exp_map:
            clause.plain_explanation = exp_map[clause.id]

    logger.info(f"Pipeline complete: {len(clauses)} clauses processed concurrently")
    return pages, clauses, classification
