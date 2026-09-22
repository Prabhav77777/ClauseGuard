"""Legal analysis orchestration service.

Coordinates Q&A and scenario analysis flows:
1. Retrieve relevant clauses (never the full document)
2. Call the appropriate prompt module
3. Run final response validation
4. Return validated response

Efficiency: Only top-k relevant clauses are sent to LLM prompts,
never the full document. This reduces token usage and improves
response quality by focusing on relevant context.
"""

import logging
from backend.models.schemas import (
    Clause, QAResponse, ScenarioResponse, CertaintyLevel
)
from backend.services.retriever import ClauseRetriever
from backend.prompts.qa import answer_question
from backend.prompts.scenario import analyze_scenario
from backend.prompts.validation import validate_final_response

logger = logging.getLogger(__name__)


async def ask_question_about_document(
    question: str,
    clauses: list[Clause],
    retriever: ClauseRetriever,
    top_k: int = 5
) -> QAResponse:
    """Answer a question using evidence-grounded retrieval and validation.
    
    Pipeline:
    1. Retrieve top-k relevant clauses
    2. Generate answer from relevant clauses only
    3. Validate response (clause ID check, leak detection, claim verification)
    4. Return validated response
    """
    # Step 1: Retrieve relevant clauses
    retrieved = retriever.retrieve(question, top_k=top_k)
    logger.info(f"Retrieved {len(retrieved)} clauses for question")
    
    # Step 2: Generate answer
    response = await answer_question(question, retrieved)
    
    # Step 3: Final validation guard
    validation = validate_final_response(response, clauses)
    
    if not validation.passed and validation.corrected_response:
        logger.info("Response corrected by final validation guard")
        response = QAResponse(**validation.corrected_response)
    
    return response


async def analyze_scenario_for_document(
    scenario: str,
    clauses: list[Clause],
    retriever: ClauseRetriever,
    top_k: int = 7
) -> ScenarioResponse:
    """Analyze a hypothetical scenario with cross-category retrieval.
    
    Uses category-diverse retrieval to pull clauses from multiple
    document areas relevant to the scenario.
    """
    # Step 1: Retrieve with category diversity
    retrieved = retriever.retrieve_by_categories(scenario, top_k=top_k)
    logger.info(f"Retrieved {len(retrieved)} diverse clauses for scenario")
    
    # Step 2: Analyze scenario
    response = await analyze_scenario(scenario, retrieved)
    
    # Step 3: Final validation guard
    validation = validate_final_response(response, clauses)
    
    if not validation.passed and validation.corrected_response:
        logger.info("Scenario response corrected by final validation guard")
        response = ScenarioResponse(**validation.corrected_response)
    
    return response
