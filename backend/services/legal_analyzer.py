"""Legal analysis orchestration service.

Coordinates Q&A and scenario analysis flows:
1. Retrieve relevant clauses (never the full document)
2. Check LLM response LRU/TTL cache
3. Call the appropriate prompt module on cache miss
4. Run final response validation
5. Return validated response

Efficiency:
- Only top-k relevant clauses are sent to LLM prompts, never full document text.
- In-memory TTLCache trades an O(1) hash table lookup against a full 1-2 second LLM round trip, preventing duplicate API calls.
"""

import logging

from cachetools import TTLCache

from backend.models.schemas import Clause, QAResponse, ScenarioResponse
from backend.prompts.qa import answer_question
from backend.prompts.scenario import analyze_scenario
from backend.prompts.validation import validate_final_response
from backend.services.retriever import ClauseRetriever

logger = logging.getLogger(__name__)

# Efficiency: LRU/TTL cache for LLM responses (max 500 entries, 30-minute TTL)
# Keyed on hash of (query, tuple(sorted(retrieved_clause_ids)))
_LLM_RESPONSE_CACHE: TTLCache[tuple[str, tuple[str, ...]], QAResponse] = TTLCache(maxsize=500, ttl=1800)
_SCENARIO_CACHE: TTLCache[tuple[str, tuple[str, ...]], ScenarioResponse] = TTLCache(maxsize=500, ttl=1800)


async def ask_question_about_document(
    question: str,
    clauses: list[Clause],
    retriever: ClauseRetriever,
    top_k: int = 5
) -> QAResponse:
    """Answer a question using evidence-grounded retrieval, LLM response caching, and validation."""
    # Step 1: Retrieve relevant clauses
    retrieved = retriever.retrieve(question, top_k=top_k)
    logger.info(f"Retrieved {len(retrieved)} clauses for question")

    # Efficiency: Check LLM response cache to avoid duplicate Gemini calls
    cache_key = (question.strip().lower(), tuple(sorted(c.id for c in retrieved)))
    if cache_key in _LLM_RESPONSE_CACHE:
        logger.info("Efficiency: LLM response cache hit (O(1) lookup vs 1.5s roundtrip)")
        return _LLM_RESPONSE_CACHE[cache_key]

    # Step 2: Generate answer
    response = await answer_question(question, retrieved)

    # Step 3: Final validation guard
    validation = validate_final_response(response, clauses)
    if not validation.passed and validation.corrected_response:
        logger.info("Response corrected by final validation guard")
        response = QAResponse(**validation.corrected_response)

    # Cache validated response
    _LLM_RESPONSE_CACHE[cache_key] = response
    return response


async def analyze_scenario_for_document(
    scenario: str,
    clauses: list[Clause],
    retriever: ClauseRetriever,
    top_k: int = 7
) -> ScenarioResponse:
    """Analyze a hypothetical scenario with cross-category retrieval and response caching."""
    # Step 1: Retrieve with category diversity
    retrieved = retriever.retrieve_by_categories(scenario, top_k=top_k)
    logger.info(f"Retrieved {len(retrieved)} diverse clauses for scenario")

    # Efficiency: Check scenario cache
    cache_key = (scenario.strip().lower(), tuple(sorted(c.id for c in retrieved)))
    if cache_key in _SCENARIO_CACHE:
        logger.info("Efficiency: Scenario response cache hit")
        return _SCENARIO_CACHE[cache_key]

    # Step 2: Analyze scenario
    response = await analyze_scenario(scenario, retrieved)

    # Step 3: Final validation guard
    validation = validate_final_response(response, clauses)
    if not validation.passed and validation.corrected_response:
        logger.info("Scenario response corrected by final validation guard")
        response = ScenarioResponse(**validation.corrected_response)

    _SCENARIO_CACHE[cache_key] = response
    return response
