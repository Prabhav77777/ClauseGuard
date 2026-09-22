"""Scenario analysis prompt.

Reasons about hypothetical scenarios (e.g., 'What happens if I resign after 4 months?')
by pulling and reasoning across multiple relevant clauses from different categories.

Implications are always labeled as interpretation, never as legal conclusions.
"""

import anthropic
import logging
from backend.config import settings
from backend.models.schemas import Clause, ScenarioResponse
from backend.security.prompt_guard import wrap_document_content, get_data_boundary_instruction

logger = logging.getLogger(__name__)


async def analyze_scenario(scenario: str, retrieved_clauses: list[Clause]) -> ScenarioResponse:
    """Analyze a hypothetical scenario against relevant clauses.
    
    Retrieves clauses across multiple categories to reason about
    cross-cutting implications of a scenario.
    """
    if not retrieved_clauses:
        return ScenarioResponse(
            relevant_clauses=[],
            what_document_says="No relevant clauses were found for this scenario.",
            potential_implication="Without relevant clauses, no implications can be drawn.",
            unclear="The document does not appear to address this scenario.",
            lawyer_question="You should ask your lawyer how this scenario would be handled under the agreement."
        )
    
    clauses_text = ""
    clause_ids = []
    for clause in retrieved_clauses:
        clauses_text += f"\nClause ID: {clause.id}\nCategory: {clause.category.value if clause.category else 'general'}\nSection: {clause.section}\nPage: {clause.page}\nText: {clause.text}\n---\n"
        clause_ids.append(clause.id)
    
    wrapped_text, nonce = wrap_document_content(clauses_text)
    boundary_instruction = get_data_boundary_instruction(nonce)
    available_ids = ", ".join(clause_ids)
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2048,
        system=f"""You are ClauseGuard, a legal document analysis assistant. Analyze hypothetical scenarios against relevant contract clauses.

{boundary_instruction}

You are NOT a lawyer. You do NOT provide legal advice or conclusions about enforceability.

For the given scenario, analyze:
1. 'what_document_says': What the document EXPLICITLY states that is relevant (quote relevant text)
2. 'potential_implication': What could REASONABLY be inferred (ALWAYS label this as "Based on interpretation of the clauses..." - never state as fact or legal conclusion)
3. 'unclear': What CANNOT be determined and would need clarification
4. 'lawyer_question': A specific, actionable question the user should ask their lawyer

Rules:
1. ONLY cite clause IDs from this list: {available_ids}
2. Implications must be labeled as interpretation, NEVER as legal conclusions
3. Never fabricate clauses, dates, penalties, or obligations
4. Consider how multiple clauses might interact with each other
5. If the scenario involves timing, look for probation periods, notice periods, and effective dates""",
        tools=[{
            "name": "analyze_scenario",
            "description": "Output scenario analysis.",
            "input_schema": ScenarioResponse.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "analyze_scenario"},
        messages=[{"role": "user", "content": f"Scenario: {scenario}\n\nRelevant clauses from the document:\n{wrapped_text}"}]
    )
    
    for block in response.content:
        if block.type == "tool_use":
            result = ScenarioResponse(**block.input)
            logger.info(f"Scenario analysis with {len(result.relevant_clauses)} relevant clauses")
            return result
    
    return ScenarioResponse(
        relevant_clauses=[],
        what_document_says="Unable to analyze this scenario.",
        potential_implication="",
        unclear="The analysis could not be completed.",
        lawyer_question="Please consult your lawyer about this scenario."
    )
