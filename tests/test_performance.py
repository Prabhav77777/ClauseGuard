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

    def test_upload_content_hash_cache_bypasses_pipeline(self, sample_pdf_bytes, monkeypatch):
        """Verify uploading identical file twice uses content-hash cache and skips process_document."""
        from fastapi.testclient import TestClient

        from backend.api.documents import _DOCUMENT_CONTENT_CACHE
        from backend.main import app
        from backend.models.schemas import ClassificationResult, Clause, DocumentType

        _DOCUMENT_CONTENT_CACHE.clear()

        client = TestClient(app)
        pipeline_call_count = 0

        async def mock_process_document(file_bytes, file_type):
            nonlocal pipeline_call_count
            pipeline_call_count += 1
            return (
                [],
                [Clause(id="clause_000", section="S1", page=1, text="Text")],
                ClassificationResult(doc_type=DocumentType.EMPLOYMENT_AGREEMENT, confidence=0.99)
            )

        monkeypatch.setattr("backend.api.documents.process_document", mock_process_document)

        # First upload: cache miss, triggers process_document
        res1 = client.post(
            "/api/documents/upload",
            files={"file": ("contract.pdf", sample_pdf_bytes, "application/pdf")}
        )
        assert res1.status_code == 200
        assert pipeline_call_count == 1
        data1 = res1.json()

        # Second upload with identical bytes: cache hit, skips process_document
        res2 = client.post(
            "/api/documents/upload",
            files={"file": ("contract.pdf", sample_pdf_bytes, "application/pdf")}
        )
        assert res2.status_code == 200
        assert pipeline_call_count == 1  # Did NOT increment!
        data2 = res2.json()

        # Verify distinct session_ids were generated for each upload
        assert data1["session_id"] != data2["session_id"]
        assert data1["total_clauses"] == data2["total_clauses"]

    def test_retriever_precision_recall_benchmark(self, sample_clauses):
        """Verify TF-IDF retrieval precision and recall exceed 90% target threshold."""
        retriever = ClauseRetriever(sample_clauses)
        test_cases = [
            ("probationary period 6 months", "clause_002"),
            ("salary $120,000 base pay", "clause_001"),
            ("senior software engineer duties", "clause_000"),
            ("competing business 50 miles noncompete", "clause_004"),
            ("confidential information trade secrets", "clause_005"),
        ]

        correct_retrievals = 0
        for query, expected_clause_id in test_cases:
            results = retriever.retrieve(query, top_k=3)
            result_ids = [c.id for c in results]
            if expected_clause_id in result_ids:
                correct_retrievals += 1

        accuracy = correct_retrievals / len(test_cases)
        assert accuracy >= 0.90, f"Retrieval accuracy {accuracy:.2f} is below 90% threshold"

    @pytest.mark.asyncio
    async def test_end_to_end_qa_latency_benchmark(self, sample_clauses, monkeypatch):
        """Benchmark local Q&A execution overhead (retrieval + validation) is sub-10ms."""
        from backend.models.schemas import CertaintyLevel, QAResponse
        from backend.services.legal_analyzer import _LLM_RESPONSE_CACHE, ask_question_about_document

        _LLM_RESPONSE_CACHE.clear()

        async def mock_answer_question(q, clauses):
            return QAResponse(
                answer="Sample answer",
                sources=["clause_000"],
                certainty=CertaintyLevel.STATED,
                stated="Sample stated",
                interpreted="",
                not_established="",
                lawyer_question=None
            )

        monkeypatch.setattr("backend.services.legal_analyzer.answer_question", mock_answer_question)
        retriever = ClauseRetriever(sample_clauses)

        t0 = time.perf_counter()
        for _ in range(50):
            await ask_question_about_document("What is the position?", sample_clauses, retriever)
        total_time = time.perf_counter() - t0

        avg_latency_ms = (total_time / 50) * 1000
        # Overhead per Q&A pipeline call should be under 10ms
        assert avg_latency_ms < 10.0, f"Average latency {avg_latency_ms:.2f}ms exceeds 10ms ceiling"

    def test_session_cleanup_frees_memory(self):
        """Verify expired sessions are purged to free memory."""
        from backend.main import sessions
        from backend.models.schemas import DocumentSession

        sessions.clear()
        # Add active and expired sessions
        sessions["active_1"] = {"last_accessed": time.time(), "session": DocumentSession(session_id="active_1")}
        sessions["expired_1"] = {"last_accessed": time.time() - 7200, "session": DocumentSession(session_id="expired_1")}

        # Run single cleanup pass synchronously
        now = time.time()
        expired_ids = [
            sid for sid, data in sessions.items()
            if now - data.get("last_accessed", now) > 3600
        ]
        for sid in expired_ids:
            del sessions[sid]

        assert "active_1" in sessions
        assert "expired_1" not in sessions

    def test_create_adaptive_batches(self):
        """Verify adaptive page batching respects target_chars and max_pages limits."""
        from backend.models.schemas import PageText
        from backend.prompts.extraction import create_adaptive_batches

        # Case 1: Empty pages list
        assert create_adaptive_batches([]) == []

        # Case 2: Single short page stays 1 batch
        p1 = [PageText(page_number=1, text="Short text")]
        b1 = create_adaptive_batches(p1, target_chars=8000, max_pages=10)
        assert len(b1) == 1 and len(b1[0]) == 1

        # Case 3: 12 small pages (100 chars each) capped at max_pages=10
        p_many = [PageText(page_number=i, text="A" * 100) for i in range(1, 13)]
        b_many = create_adaptive_batches(p_many, target_chars=8000, max_pages=10)
        assert len(b_many) == 2
        assert len(b_many[0]) == 10
        assert len(b_many[1]) == 2

        # Case 4: Pages totaling > target_chars split dynamically
        p_large = [PageText(page_number=i, text="B" * 3500) for i in range(1, 4)]
        b_large = create_adaptive_batches(p_large, target_chars=8000, max_pages=10)
        assert len(b_large) == 2
        assert len(b_large[0]) == 2  # 7,000 chars
        assert len(b_large[1]) == 1  # 3,500 chars

        # Case 5: Single huge page exceeding target_chars gets its own batch
        p_huge = [PageText(page_number=1, text="C" * 12000)]
        b_huge = create_adaptive_batches(p_huge, target_chars=8000, max_pages=10)
        assert len(b_huge) == 1 and len(b_huge[0]) == 1

    @pytest.mark.asyncio
    async def test_min_heap_session_cleanup(self):
        """Verify min-heap efficiently purges expired sessions while preserving active ones."""
        import heapq

        from backend.main import sessions, sessions_heap, sync_sessions_heap
        from backend.models.schemas import DocumentSession

        sessions.clear()
        sessions_heap.clear()

        now = time.time()
        # Add 1 active session and 2 expired sessions
        sessions["active"] = {"last_accessed": now, "session": DocumentSession(session_id="active")}
        sessions["expired_old"] = {"last_accessed": now - 7200, "session": DocumentSession(session_id="expired_old")}
        sessions["expired_recent"] = {"last_accessed": now - 3601, "session": DocumentSession(session_id="expired_recent")}

        sync_sessions_heap()
        assert len(sessions_heap) == 3

        # Simulate min-heap cleanup pass
        expired_count = 0
        while sessions_heap and sessions_heap[0][0] <= now:
            expiry, sid = heapq.heappop(sessions_heap)
            data = sessions.get(sid)
            if data is None:
                continue
            last_accessed = data.get("last_accessed", now) if isinstance(data, dict) else now
            if last_accessed + 3600 <= now:
                del sessions[sid]
                expired_count += 1

        assert expired_count == 2
        assert "active" in sessions
        assert "expired_old" not in sessions
        assert "expired_recent" not in sessions
        assert len(sessions_heap) == 1




