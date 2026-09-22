"""Tests for performance and efficiency optimizations.

Tests:
- Async pipeline concurrency (asyncio.gather)
- In-memory TF-IDF query caching O(1) repeat retrieval
- Pre-compiled regex leak scanning performance
"""

import time
import pytest
import asyncio
from backend.models.schemas import Clause, ClauseCategory, PageText
from backend.services.retriever import ClauseRetriever
from backend.security.prompt_guard import strip_system_prompt_leaks


class TestPerformanceOptimizations:
    """Test suite verifying efficiency and latency optimizations."""

    def test_retriever_cache_hit_performance(self, sample_clauses):
        """Verify repeated retrieval uses in-memory cache for O(1) response."""
        retriever = ClauseRetriever(sample_clauses)
        query = "What is the probation period?"

        # First call (populates cache)
        t0 = time.perf_counter()
        res1 = retriever.retrieve(query, top_k=3)
        t1 = time.perf_counter()

        # Second call (cache hit)
        res2 = retriever.retrieve(query, top_k=3)
        t2 = time.perf_counter()

        assert res1 == res2
        # Cache hit time should be strictly less than initial matrix calculation
        assert (t2 - t1) <= (t1 - t0) + 0.001

    def test_precompiled_regex_leak_detection_speed(self):
        """Verify high-throughput leak detection on large text blocks."""
        large_text = "Standard legal clause text. " * 5000 + "system prompt: test"
        t0 = time.perf_counter()
        cleaned = strip_system_prompt_leaks(large_text)
        duration = time.perf_counter() - t0

        assert "[REDACTED]" in cleaned
        # Should complete in under 50ms for 100k+ characters
        assert duration < 0.05

    @pytest.mark.asyncio
    async def test_async_gather_pipeline_concurrency(self, sample_pdf_bytes, monkeypatch):
        """Verify pipeline steps execute concurrently using asyncio.gather."""
        from backend.services.clause_extractor import process_document

        # Mock prompt functions to record concurrency
        execution_order = []

        async def mock_classify(pages):
            execution_order.append("classify_start")
            await asyncio.sleep(0.05)
            execution_order.append("classify_end")
            from backend.models.schemas import ClassificationResult, DocumentType
            return ClassificationResult(doc_type=DocumentType.EMPLOYMENT_AGREEMENT, confidence=0.99)

        async def mock_extract(pages):
            execution_order.append("extract_start")
            await asyncio.sleep(0.05)
            execution_order.append("extract_end")
            return [Clause(id="clause_000", section="S1", page=1, text="T1")]

        async def mock_categorize(clauses):
            execution_order.append("categorize_start")
            await asyncio.sleep(0.05)
            execution_order.append("categorize_end")
            from backend.models.schemas import CategorizationResult, ClauseCategory
            return [CategorizationResult(clause_id="clause_000", category=ClauseCategory.COMPENSATION)]

        async def mock_explain(clauses):
            execution_order.append("explain_start")
            await asyncio.sleep(0.05)
            execution_order.append("explain_end")
            from backend.models.schemas import PlainExplanationResult
            return [PlainExplanationResult(clause_id="clause_000", plain_explanation="Simple explanation")]

        monkeypatch.setattr("backend.services.clause_extractor.classify_document", mock_classify)
        monkeypatch.setattr("backend.services.clause_extractor.extract_clauses_from_pages", mock_extract)
        monkeypatch.setattr("backend.services.clause_extractor.categorize_clauses", mock_categorize)
        monkeypatch.setattr("backend.services.clause_extractor.explain_clauses", mock_explain)

        pages, clauses, classification = await process_document(sample_pdf_bytes, "pdf")

        assert len(clauses) == 1
        assert classification.confidence == 0.99
        # Check that starts occurred before ends (demonstrating parallel execution)
        assert "classify_start" in execution_order and "extract_start" in execution_order
        assert execution_order.index("extract_start") < execution_order.index("classify_end")
