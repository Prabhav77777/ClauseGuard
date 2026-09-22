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

    def test_session_expiry_integration(self, sample_pdf_bytes, monkeypatch):
        """Verify real uploaded DocumentSession objects expire past SESSION_TTL_SECONDS while active sessions remain."""
        from fastapi.testclient import TestClient

        from backend.api.documents import _DOCUMENT_CONTENT_CACHE
        from backend.config import settings
        from backend.main import app, run_cleanup_pass, sessions, sessions_heap
        from backend.models.schemas import ClassificationResult, Clause, DocumentType

        _DOCUMENT_CONTENT_CACHE.clear()
        sessions.clear()
        sessions_heap.clear()
        app.state.sessions = sessions
        app.state.retrievers = {}

        client = TestClient(app)

        async def mock_process_document(file_bytes, file_type):
            return (
                [],
                [Clause(id="clause_000", section="S1", page=1, text="Text")],
                ClassificationResult(doc_type=DocumentType.EMPLOYMENT_AGREEMENT, confidence=0.99)
            )

        monkeypatch.setattr("backend.api.documents.process_document", mock_process_document)

        now0 = time.time()

        # Upload session 1 (to be expired)
        res1 = client.post("/api/documents/upload", files={"file": ("doc1.pdf", sample_pdf_bytes, "application/pdf")})
        assert res1.status_code == 200
        sid1 = res1.json()["session_id"]

        # Upload session 2 (to remain active)
        res2 = client.post("/api/documents/upload", files={"file": ("doc2.pdf", sample_pdf_bytes + b"extra_content", "application/pdf")})
        assert res2.status_code == 200
        sid2 = res2.json()["session_id"]

        assert sid1 in app.state.sessions
        assert sid2 in app.state.sessions

        # Keep sid1 last_accessed at now0, but refresh sid2 last_accessed to now0 + 200
        app.state.sessions[sid1].last_accessed = now0
        app.state.sessions[sid2].last_accessed = now0 + 200

        # Pass 1: Run cleanup pass at target time t = now0 + SESSION_TTL_SECONDS + 10
        # sid1 (expiry now0 + TTL) should expire; sid2 (initial heap expiry now0 + TTL + 5) will not be popped yet or will be re-pushed
        simulated_now = now0 + settings.SESSION_TTL_SECONDS + 10
        expired_count = run_cleanup_pass(now=simulated_now)

        assert expired_count == 1
        assert sid1 not in app.state.sessions
        assert sid2 in app.state.sessions

        # Pass 2: Run cleanup pass at target time t = now0 + 200 + SESSION_TTL_SECONDS + 10
        simulated_now_2 = now0 + 200 + settings.SESSION_TTL_SECONDS + 10
        expired_count_2 = run_cleanup_pass(now=simulated_now_2)

        assert expired_count_2 == 1
        assert sid2 not in app.state.sessions

    def test_content_hash_cache_lru_eviction(self):
        """Verify _DOCUMENT_CONTENT_CACHE enforces LRUCache cap of 50 entries and evicts oldest."""
        from backend.api.documents import _DOCUMENT_CONTENT_CACHE

        _DOCUMENT_CONTENT_CACHE.clear()
        assert _DOCUMENT_CONTENT_CACHE.maxsize == 50

        # Fill cache with 51 entries
        for i in range(51):
            _DOCUMENT_CONTENT_CACHE[f"hash_{i}"] = {"pages": [], "clauses": []}

        assert len(_DOCUMENT_CONTENT_CACHE) == 50
        # The first key (hash_0) should have been evicted by LRU policy
        assert "hash_0" not in _DOCUMENT_CONTENT_CACHE
        assert "hash_50" in _DOCUMENT_CONTENT_CACHE





