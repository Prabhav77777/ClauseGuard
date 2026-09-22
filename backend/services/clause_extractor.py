"""Clause extraction orchestration service.

Coordinates the full document processing pipeline:
1. Parse document into pages
2. Classify document type
3. Extract clauses with page references
4. Categorize clauses into fixed taxonomy
5. Generate plain-language explanations

Efficiency: Each step's output is cached in the session. The full pipeline
runs once per document upload, and all downstream operations (Q&A, scenario)
use the cached clause list.
"""

import logging
from backend.models.schemas import (
    Clause, PageText, DocumentType, ClassificationResult
)
from backend.services.document_parser import parse_document
from backend.prompts.extraction import classify_document, extract_clauses_from_pages
from backend.prompts.categorization import categorize_clauses
from backend.prompts.explanation import explain_clauses

logger = logging.getLogger(__name__)


async def process_document(
    file_bytes: bytes, file_type: str
) -> tuple[list[PageText], list[Clause], ClassificationResult]:
    """Run the complete document processing pipeline.
    
    Returns:
        Tuple of (raw_pages, processed_clauses, classification)
    """
    # Step 1: Parse document into page-indexed text
    logger.info(f"Step 1/5: Parsing {file_type} document...")
    pages = await parse_document(file_bytes, file_type)
    logger.info(f"Parsed {len(pages)} pages")
    
    # Step 2: Classify document type
    logger.info("Step 2/5: Classifying document type...")
    classification = await classify_document(pages)
    logger.info(f"Document classified as: {classification.doc_type} (confidence: {classification.confidence})")
    
    # Step 3: Extract clauses with page references
    logger.info("Step 3/5: Extracting clauses...")
    clauses = await extract_clauses_from_pages(pages)
    logger.info(f"Extracted {len(clauses)} clauses")
    
    if not clauses:
        logger.warning("No clauses extracted from document")
        return pages, [], classification
    
    # Step 4: Categorize clauses
    logger.info("Step 4/5: Categorizing clauses...")
    categorizations = await categorize_clauses(clauses)
    
    # Apply categories to clauses
    cat_map = {cat.clause_id: cat.category for cat in categorizations}
    for clause in clauses:
        if clause.id in cat_map:
            clause.category = cat_map[clause.id]
    
    # Step 5: Generate plain-language explanations
    logger.info("Step 5/5: Generating explanations...")
    explanations = await explain_clauses(clauses)
    
    # Apply explanations to clauses
    exp_map = {exp.clause_id: exp.plain_explanation for exp in explanations}
    for clause in clauses:
        if clause.id in exp_map:
            clause.plain_explanation = exp_map[clause.id]
    
    logger.info(f"Pipeline complete: {len(clauses)} clauses processed")
    return pages, clauses, classification
