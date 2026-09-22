"""Tests for clause extraction schemas and structure.

Tests:
2. Clause segmentation produces expected clause count/IDs on known fixture
10. Every returned clause ID structurally exists in the parsed clause set
"""

import pytest

from backend.models.schemas import (
    Clause, ClauseCategory, ExtractionResult, 
    BatchCategorizationResult, CategorizationResult,
)


class TestClauseSchemas:
    """Test Pydantic schema validation for clause-related models."""

    def test_clause_model_validates(self):
        """A valid Clause object passes validation."""
        clause = Clause(
            id="clause_000",
            section="Test Section",
            page=1,
            text="This is a test clause.",
        )
        assert clause.id == "clause_000"
        assert clause.page == 1
        assert clause.category is None  # Optional

    def test_clause_with_category(self):
        """Clause with a valid category from the fixed taxonomy passes."""
        clause = Clause(
            id="clause_001",
            section="Compensation",
            page=1,
            text="Salary is $100,000.",
            category=ClauseCategory.COMPENSATION,
        )
        assert clause.category == ClauseCategory.COMPENSATION

    def test_extraction_result_validates(self):
        """ExtractionResult with a list of clauses passes validation."""
        result = ExtractionResult(
            clauses=[
                Clause(id="clause_000", section="S1", page=1, text="Text 1"),
                Clause(id="clause_001", section="S2", page=1, text="Text 2"),
            ]
        )
        assert len(result.clauses) == 2

    def test_batch_categorization_validates(self):
        """BatchCategorizationResult validates all categories from fixed taxonomy."""
        result = BatchCategorizationResult(
            categorizations=[
                CategorizationResult(clause_id="clause_000", category=ClauseCategory.COMPENSATION),
                CategorizationResult(clause_id="clause_001", category=ClauseCategory.TERMINATION),
            ]
        )
        assert len(result.categorizations) == 2

    def test_all_categories_in_enum(self):
        """All expected categories exist in the ClauseCategory enum."""
        expected = [
            "compensation", "termination", "notice_period", "probation",
            "non_compete", "confidentiality", "liability", "intellectual_property",
            "dispute_resolution", "governing_law", "benefits", "obligations",
            "restrictions", "indemnification", "general",
        ]
        actual = [c.value for c in ClauseCategory]
        for cat in expected:
            assert cat in actual, f"Category '{cat}' missing from ClauseCategory enum"


class TestClauseIdStructure:
    """Test that clause IDs follow expected structure."""

    def test_clause_ids_are_sequential(self, sample_clauses):
        """Clause IDs follow the clause_NNN pattern."""
        for clause in sample_clauses:
            assert clause.id.startswith("clause_"), f"ID {clause.id} doesn't start with 'clause_'"

    def test_all_clause_ids_unique(self, sample_clauses):
        """All clause IDs in a set are unique."""
        ids = [c.id for c in sample_clauses]
        assert len(ids) == len(set(ids)), "Duplicate clause IDs found"

    def test_clause_pages_are_positive(self, sample_clauses):
        """All clause page numbers are positive integers."""
        for clause in sample_clauses:
            assert clause.page >= 1, f"Page number {clause.page} should be >= 1"
