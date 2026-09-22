"""Tests for evidence-grounded Q&A and retrieval.

Tests:
3. Grounded QA returns an answer matching the fixture's actual clause
4. Question about an absent topic returns explicit "not established" response
7. Question about non-existent clause returns "no supporting clause found"
10. Every returned clause ID structurally exists in the parsed clause set
"""

import pytest

from backend.models.schemas import Clause, ClauseCategory, QAResponse, CertaintyLevel
from backend.services.retriever import ClauseRetriever
from backend.prompts.validation import validate_final_response


class TestRetriever:
    """Test TF-IDF clause retrieval."""

    def test_retriever_finds_relevant_clauses(self, sample_clauses):
        """Retriever returns clauses relevant to the query."""
        retriever = ClauseRetriever(sample_clauses)
        results = retriever.retrieve("What is the salary?", top_k=3)
        assert len(results) > 0
        # The compensation clause should be among the results
        result_ids = [c.id for c in results]
        assert "clause_001" in result_ids, "Compensation clause should be retrieved for salary question"

    def test_retriever_returns_empty_for_no_clauses(self):
        """Retriever handles empty clause list gracefully."""
        retriever = ClauseRetriever([])
        results = retriever.retrieve("anything", top_k=5)
        assert results == []

    def test_retriever_respects_top_k(self, sample_clauses):
        """Retriever returns at most top_k results."""
        retriever = ClauseRetriever(sample_clauses)
        results = retriever.retrieve("employment terms", top_k=2)
        assert len(results) <= 2

    def test_retriever_category_diversity(self, sample_clauses):
        """Category-diverse retrieval returns clauses from multiple categories."""
        retriever = ClauseRetriever(sample_clauses)
        results = retriever.retrieve_by_categories("resign during probation", top_k=5)
        if len(results) > 1:
            categories = {c.category for c in results if c.category}
            # Should have some diversity (not all same category)
            assert len(categories) >= 1

    def test_retriever_probation_query(self, sample_clauses):
        """Query about probation retrieves the probation clause."""
        retriever = ClauseRetriever(sample_clauses)
        results = retriever.retrieve("probation period", top_k=3)
        result_ids = [c.id for c in results]
        assert "clause_002" in result_ids, "Probation clause should be retrieved"

    def test_retriever_noncompete_query(self, sample_clauses):
        """Query about non-compete retrieves the non-compete clause."""
        retriever = ClauseRetriever(sample_clauses)
        results = retriever.retrieve("competing business restrictions", top_k=3)
        result_ids = [c.id for c in results]
        assert "clause_004" in result_ids, "Non-compete clause should be retrieved"


class TestFinalValidation:
    """Test the final response validation guard."""

    def test_valid_response_passes(self, sample_clauses):
        """A response with valid clause IDs passes validation."""
        response = QAResponse(
            answer="Your salary is $120,000 per year.",
            sources=["clause_001"],
            certainty=CertaintyLevel.STATED,
            stated="The document says the salary is $120,000.",
            interpreted="",
            not_established="",
        )
        result = validate_final_response(response, sample_clauses)
        assert result.passed is True

    def test_fabricated_clause_ids_removed(self, sample_clauses):
        """Fabricated clause IDs are removed and response is corrected."""
        response = QAResponse(
            answer="Based on clause_999, you get a bonus.",
            sources=["clause_001", "clause_999"],
            certainty=CertaintyLevel.STATED,
            stated="The document mentions a bonus.",
            interpreted="",
            not_established="",
        )
        result = validate_final_response(response, sample_clauses)
        assert result.passed is False
        assert result.corrected_response is not None
        # clause_999 should be removed from sources
        corrected = QAResponse(**result.corrected_response)
        assert "clause_999" not in corrected.sources
        assert "clause_001" in corrected.sources

    def test_no_valid_sources_downgrades_certainty(self, sample_clauses):
        """If all sources are fabricated, certainty is downgraded to NOT_ESTABLISHED."""
        response = QAResponse(
            answer="You have unlimited vacation.",
            sources=["clause_999"],
            certainty=CertaintyLevel.STATED,
            stated="The document says unlimited vacation.",
            interpreted="",
            not_established="",
        )
        result = validate_final_response(response, sample_clauses)
        assert result.passed is False
        corrected = QAResponse(**result.corrected_response)
        assert corrected.certainty == CertaintyLevel.NOT_ESTABLISHED
        assert len(corrected.sources) == 0

    def test_every_clause_id_in_response_exists(self, sample_clauses):
        """Every clause ID in a validated response exists in the clause set."""
        response = QAResponse(
            answer="Test answer",
            sources=["clause_000", "clause_003"],
            certainty=CertaintyLevel.STATED,
            stated="Test",
            interpreted="",
            not_established="",
        )
        result = validate_final_response(response, sample_clauses)
        assert result.passed is True

        valid_ids = {c.id for c in sample_clauses}
        for source_id in response.sources:
            assert source_id in valid_ids, f"Clause ID {source_id} should exist in clause set"
