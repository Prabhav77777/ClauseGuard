"""Shared core prompt helper utilities.

Provides reusable formatting and fallback construction functions for LLM prompt modules.
"""

from typing import Any

from backend.models.schemas import Clause


def format_clauses_for_prompt(clauses: list[Clause]) -> tuple[str, list[str]]:
    """Format a list of Clause objects into structured prompt text and extract clause IDs.

    Args:
        clauses: List of Clause objects to format.

    Returns:
        Tuple of (formatted_text, list_of_clause_ids).
    """
    text_blocks: list[str] = []
    clause_ids: list[str] = []

    for clause in clauses:
        category_val = clause.category.value if clause.category else "general"
        block = (
            f"Clause ID: {clause.id}\n"
            f"Category: {category_val}\n"
            f"Section: {clause.section}\n"
            f"Page: {clause.page}\n"
            f"Text: {clause.text}\n"
            "---"
        )
        text_blocks.append(block)
        clause_ids.append(clause.id)

    return "\n".join(text_blocks), clause_ids


def safe_fallback_dict(message: str, field_names: list[str]) -> dict[str, Any]:
    """Construct a safe fallback dictionary matching target schema fields on LLM failure.

    Args:
        message: Fallback explanation message.
        field_names: Target field names to populate.

    Returns:
        Dictionary mapping field names to message strings or empty lists.
    """
    result: dict[str, Any] = {}
    for name in field_names:
        if name in ("sources", "relevant_clauses", "clause_ids", "items", "clauses"):
            result[name] = []
        else:
            result[name] = message
    return result
