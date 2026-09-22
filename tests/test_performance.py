"""Tests for performance and efficiency optimizations.

Tests:
- Async pipeline concurrency (asyncio.gather)
- In-memory TF-IDF query caching O(1) repeat retrieval
- Pre-compiled regex leak scanning performance
"""

import asyncio
import time

import pytest

from backend.models.schemas import Clause, ClauseCategory
from backend.security.prompt_guard import strip_system_prompt_leaks
from backend.services.retriever import ClauseRetriever


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
            from backend.models.schemas import CategorizationResult
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

    @pytest.mark.asyncio
    async def test_ttl_cache_deduplicates_llm_calls(self, sample_clauses, monkeypatch):
        """Verify duplicate questions use TTLCache and avoid invoking Gemini prompt functions a second time."""
        from backend.models.schemas import CertaintyLevel, QAResponse
        from backend.services.legal_analyzer import _LLM_RESPONSE_CACHE, ask_question_about_document

        _LLM_RESPONSE_CACHE.clear()

        call_count = 0

        async def mock_answer_question(q, clauses):
            nonlocal call_count
            call_count += 1
            return QAResponse(
                answer="The probation period is 3 months.",
                sources=["clause_000"],
                certainty=CertaintyLevel.STATED,
                stated="The probation period is 3 months.",
                interpreted="",
                not_established="",
                lawyer_question=None
            )

        monkeypatch.setattr("backend.services.legal_analyzer.answer_question", mock_answer_question)

        retriever = ClauseRetriever(sample_clauses)
        question = "What is the probation period?"

        # First call: cache miss, triggers answer_question
        res1 = await ask_question_about_document(question, sample_clauses, retriever)
        assert call_count == 1
        assert res1.answer == "The probation period is 3 months."

        # Second call: cache hit, bypasses answer_question
        res2 = await ask_question_about_document(question, sample_clauses, retriever)
        assert call_count == 1  # Did NOT increment
        assert res2.answer == res1.answer

    @pytest.mark.asyncio
    async def test_sha256_parse_cache_deduplication(self, sample_pdf_bytes, monkeypatch):
        """Verify identical document bytes use SHA256 parse cache without re-parsing."""
        from backend.services.document_parser import _PARSE_CACHE, parse_document

        _PARSE_CACHE.clear()

        parse_count = 0
        original_parse_pdf_sync = __import__("backend.services.document_parser", fromlist=["_parse_pdf_sync"])._parse_pdf_sync

        def mock_parse_sync(file_bytes):
            nonlocal parse_count
            parse_count += 1
            return original_parse_pdf_sync(file_bytes)

        monkeypatch.setattr("backend.services.document_parser._parse_pdf_sync", mock_parse_sync)

        pages1 = await parse_document(sample_pdf_bytes, "pdf")
        assert parse_count == 1

        pages2 = await parse_document(sample_pdf_bytes, "pdf")
        assert parse_count == 1  # Re-used cache, didn't re-parse
        assert pages1 == pages2

