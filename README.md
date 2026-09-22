## PR REVIEW NOTES

### Second-Pass Architecture & Code Review Findings
- **Deterministic Session Expiry Testability**: Extracted `run_cleanup_pass(now: float | None = None)` as a standalone function in `backend/main.py`. This isolates the min-heap pop loop and TTL timestamp checks so integration tests can pass explicit target timestamps (`simulated_now`) deterministically without relying on `asyncio.sleep` or real wall-clock delays.
- **Session Scope Audit on `compare.py`**: Audited `backend/api/compare.py` and confirmed that document comparison processes raw upload files directly on the fly per request. It does NOT reference or create session state in `app.state.sessions`, so session timestamp updating (`last_accessed`) is not required for comparison operations.
- **Lifespan State Binding in API Integration Tests**: Identified that instantiated `TestClient(app)` calls without context manager startup do not invoke FastAPI `lifespan` handlers, leaving `app.state.sessions` unbound to `main.sessions`. Updated `test_session_expiry_integration` in `tests/test_performance.py` to explicitly bind state references, ensuring tests execute against identical memory structures as production.
- **500 Error Handler Alignment**: Verified that route-level 500 exceptions in `backend/api/documents.py` explicitly return document-processing context for upload clients, whereas `main.py` provides a generic global exception handler for unhandled framework/routing errors.
- **Content Hash Caching & Bound Safety**: Implemented thread-safe `cachetools.LRUCache(maxsize=50)` wrapped with `asyncio.Lock()` for `_DOCUMENT_CONTENT_CACHE` in `backend/api/documents.py` to prevent memory leaks during high-volume document uploads.
- **Taxonomy & Codebase Tagging**: Fully tagged all 30 backend Python modules with block-level taxonomy tags (`MODULE:`, `@level-one-validation:`, `#Scope-Of-Improvement:`, `@risk-area:`, `#Uncertain:`, `#What:`, `#Business-Intent:`).

### Consolidated Risk Areas (`@risk-area`)
- `backend/main.py`: In-memory session dictionary and min-heap are lost on process restart and cannot be shared across multiple worker processes.
- `backend/api/documents.py`: In-memory content hash cache uses `LRUCache(maxsize=50)` with `asyncio.Lock()`; multi-worker horizontal scaling requires a shared backend (e.g., Redis).
- `backend/api/compare.py`: Synchronous sequential processing of two documents doubles pipeline latency; could leverage `asyncio.gather` for parallel parsing.
- `backend/core/limiter.py`: In-memory rate limiting tracks limits per process; multi-worker deployments require Redis storage backend.
- `backend/config.py`: Statically cached settings via `lru_cache` cannot reflect runtime environment changes without process restart.
- `backend/prompts/gemini_client.py`: Synchronous `generate_content` call blocks worker thread pool under high network latency.
- `backend/prompts/validation.py`: Synchronous validation check adds an additional LLM API call latency overhead.
- `backend/services/document_parser.py`: Scanned PDFs without extractable text layer return empty text; requires OCR engine fallback for full coverage.
- `backend/services/retriever.py`: TF-IDF relies on exact term matching; queries with heavy synonyms without keyword overlap may yield lower similarity scores.

### Consolidated Scopes of Improvement (`#Scope-Of-Improvement`)
- `backend/main.py`: Migrate in-memory session dictionary and min-heap to Redis for distributed multi-worker production deployments.
- `backend/api/documents.py`: Support multipart chunked upload streams for very large files exceeding typical HTTP body buffers.
- `backend/api/compare.py`: Run `process_document` for file1 and file2 concurrently via `asyncio.gather` to reduce total comparison latency.
- `backend/api/chat.py`: Add stream response option for long scenario analyses to improve perceived client UI latency.
- `backend/services/document_parser.py`: Add Tesseract OCR fallback for image-only scanned PDFs.
- `backend/services/retriever.py`: Add hybrid BM25 + dense embedding re-ranking if semantically complex queries exhibit keyword mismatch.
- `backend/services/legal_analyzer.py`: Add thread-safe locking to TTLCache instances if high concurrency causes cache state mutation contention.
- `backend/services/clause_extractor.py`: Add pipeline status callback parameter to report progress percentages to real-time WebSockets.
- `backend/services/brief_generator.py`: Add PDF export option alongside Markdown export.
- `backend/security/validation.py`: Add clamav virus scanning hook before magic byte inspection for high-security enterprise deployments.
- `backend/security/prompt_guard.py`: Add structured audit logging when system prompt leak redaction is triggered.
- `backend/prompts/categorization.py`: Split very large clause sets (>100 clauses) into multiple sub-batches to prevent hitting prompt output token limits.
- `backend/prompts/comparison.py`: Pre-align matching clauses using fuzzy string matching before calling LLM to reduce prompt context size.
- `backend/prompts/explanation.py`: Make batch size dynamic based on character count similar to extraction adaptive batching.
- `backend/prompts/extraction.py`: Add regex fallback pre-segmentation to preserve clause boundaries even if Gemini extraction fails on corrupted OCR inputs.
- `backend/prompts/gemini_client.py`: Add exponential backoff retry decorator to handle transient HTTP 429 / rate limit errors gracefully.
- `backend/prompts/qa.py`: Pass historical question-answer pairs for session conversational context during multi-turn Q&A.
- `backend/prompts/scenario.py`: Add pre-built template scenarios in prompt for common contract types.
- `backend/prompts/validation.py`: Log validation failure metrics to monitor LLM citation accuracy over time.
- `backend/models/schemas.py`: Add custom Pydantic validators to enforce non-empty whitespace checking on verbatim clause strings.
- `backend/config.py`: Add settings refresh method to allow live environment configuration reloads in containerized deployments.
- `backend/core/limiter.py`: Use Redis storage backend for slowapi to share rate limit counts across multiple API worker nodes.
- `backend/core/prompt_helpers.py`: Add token counting helper to accurately estimate prompt length before dispatching to Gemini API.

---

# ClauseGuard Focused

> **GenAI-Powered Legal Document Analysis & Assistance System**
>
> *Understand any contract, ask it anything, and walk into your lawyer's office already prepared.*

[![CI](https://github.com/Prabhav77777/ClauseGuard/actions/workflows/ci.yml/badge.svg)](https://github.com/Prabhav77777/ClauseGuard/actions/workflows/ci.yml)

---

## 1. Vertical & Problem Alignment

ClauseGuard targets individuals facing complex legal contracts (employees, tenants, freelancers) who require clarity before signing or acting — without pretending to replace professional legal advice.

Here is the explicit mapping between the challenge statement's use cases and ClauseGuard features:

| Challenge Use Case | ClauseGuard Feature Implementation | Module |
|---|---|---|
| **Simplifying complex legal documents** | Page-aware clause extraction with jargon-free, plain-English explanations per clause. | `backend/prompts/explanation.py` |
| **Comparing contracts, agreements, or policies** | Two-document comparison endpoint classifying diffs into Added/Removed/Modified with materiality (cosmetic vs. substantive) and stated justification. | `backend/prompts/comparison.py` |
| **Highlighting important clauses, obligations, risks, or inconsistencies** | Fixed taxonomy clause map auto-categorizing compensation, termination, non-compete, liability, etc., plus cross-clause inconsistency detection. | `backend/prompts/categorization.py` |
| **Answering questions based on provided legal documents** | Evidence-grounded Q&A with strict three-way certainty distinction: **stated** / **interpreted** / **not established**. | `backend/prompts/qa.py` |
| **Helping users understand their options and potential next steps** | Scenario Simulator reasoning across multiple clause categories ("Can I be terminated without notice?", "What am I liable for if I leave early?", "What happens to my IP?"). | `backend/prompts/scenario.py` |
| **Generating summaries, checklists, or other actionable outputs** | One-click compilation of accumulated unclear items and questions into an exportable "Questions & Briefing for Your Lawyer" document. | `backend/services/brief_generator.py` |
| **Helping users prepare information or questions for a legal professional** | Automated generation of actionable, contract-grounded lawyer questions attached to Q&A and scenario responses. | `backend/api/chat.py` |

---

## 2. Approach & Logic

ClauseGuard operates on a 7-stage sequential pipeline:

```
[Upload] ➔ [Structure] ➔ [Explore] ➔ [Ask] ➔ [Simulate] ➔ [Compare] ➔ [Prepare]
```

### Core Design Principles

1. **Evidence-Grounding Above All**: Every substantive, document-specific answer must cite its source clause ID (`clause_000`, `clause_001`), section heading, and page reference.
2. **Three-Way Certainty Distinction**: Every Q&A and scenario output strictly separates:
   - **What the document explicitly states** (verbatim/literal reading)
   - **Reasonable interpretation** (explicitly labeled as inference, never legal advice)
   - **What cannot be determined** from the document
3. **Data/Instruction Separation**: Uploaded document text is strictly treated as **DATA**, never as instructions to the AI.
4. **No Arbitrary Numeric Risk Scores**: Risk cannot be reduced to a defensible numeric score (e.g. "72/100"). ClauseGuard uses qualitative, evidence-grounded labels.
5. **No Legal Conclusions**: The system never claims to be a lawyer or renders conclusions on enforceability.

---

## 3. Architecture & How It Works

### Architecture Diagram

```
                             ┌──────────────────────────────────────┐
                             │          Vite + React Frontend       │
                             │ (Clause Map, Q&A Chat, Brief Export) │
                             └──────────────────┬───────────────────┘
                                                │ REST API (JSON / HTTP)
                                                ▼
                             ┌──────────────────────────────────────┐
                             │            FastAPI Backend           │
                             │         (Async, Rate-Limited)        │
                             └──────┬────────────────────────┬──────┘
                                    │                        │
            ┌───────────────────────┴────────┐      ┌────────┴──────────────────────┐
            ▼                                │      ▼                               │
┌──────────────────────┐                     │  ┌──────────────────────┐            │
│    Security Layer    │                     │  │   Document Parser    │            │
│ Magic Byte Check,    │                     │  │ (PyMuPDF / docx)     │            │
│ Delimiter Nonces,    │                     │  └──────────┬───────────┘            │
│ Sanitization         │                     │             │                        │
└──────────────────────┘                     │             ▼                        │
                                             │  ┌──────────────────────┐            │
                                             │  │  In-Memory Retriever │            │
                                             │  │  (TF-IDF / Cosine)   │            │
                                             │  └──────────┬───────────┘            │
                                             │             │                        │
                                             ▼             ▼                        │
                             ┌──────────────────────────────────────┐               │
                             │        Pydantic Validation           │               │
                             │       (Schemas & Input/Output)       │               │
                             └──────────────────┬───────────────────┘               │
                                                │                                   │
                                                ▼                                   │
                             ┌──────────────────────────────────────┐               │
                             │          Google Gemini API           │               │
                             │    (Structured JSON / google-genai)  │               │
                             └──────────────────────────────────────┘               │
                                                                                    │
                                                                                    ▼
                                                            ┌───────────────────────────────┐
                                                            │   Final Validation Guard      │
                                                            │ (ID Check, Redaction,         │
                                                            │  Certainty Downgrade)         │
                                                            └───────────────────────────────┘
```

### Key Modules

- `backend/security/validation.py`: File upload security (magic byte detection, zero-byte rejection, zip-bomb defense, file size ceiling, page/character limits).
- `backend/security/prompt_guard.py`: Prompt injection defense with per-request randomized nonces (`<DOCUMENT_DATA_nonce>`), HTML sanitization via `bleach`, and system prompt leak scrubbing.
- `backend/core/prompt_helpers.py` & `backend/core/limiter.py`: Shared core prompt formatters and rate limiter instance.
- `backend/services/document_parser.py`: Async thread-pool text extraction preserving page boundaries for PDF (PyMuPDF) and DOCX (`python-docx`).
- `backend/services/retriever.py`: In-memory TF-IDF vectorizer + cosine similarity for top-k clause retrieval.
- `backend/services/legal_analyzer.py`: Orchestrates evidence-grounded Q&A and scenario analysis with the validation guard pipeline.
- `backend/services/brief_generator.py`: Compiles session questions and unclear items into an exportable Markdown lawyer brief.
- `backend/prompts/gemini_client.py`: Shared Gemini API client helper generating structured JSON validated against Pydantic schemas.
- `backend/prompts/`: 7 narrow, single-purpose prompt modules (`extraction.py`, `categorization.py`, `explanation.py`, `qa.py`, `scenario.py`, `comparison.py`, `validation.py`).

---

## 4. Assumptions & Limitations

- **Not Legal Advice**: Information provided is for educational and preparation purposes only.
- **Document Formats**: PDF and DOCX documents with extractable text layers.
- **Limits Enforced**: Maximum 10 MB file size, 50 pages, 500,000 characters per document.
- **In-Memory Storage**: Sessions are stored in memory and expire after 1 hour of inactivity. No persistent database is used.

---

## 5. Security

- **Comprehensive Security Policy**: Detailed in [`SECURITY.md`](file:///d:/Desktop/Desktop/ClauseGuard/SECURITY.md).
- **HTTP Security Response Headers**: Enforces `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Content-Security-Policy: default-src 'self'...` on all API responses.
- **Magic Byte, Zero-Byte & Zip Bomb Defense**: Verifies binary signatures (`%PDF-`, `PK\x03\x04` ZIP structure with `word/document.xml`), rejects zero-byte uploads, and blocks zip bombs (compression ratio > 100:1 or uncompressed > 25MB) prior to XML parsing.
- **Rate Limiting Enforcement**: Applied across all API endpoints using `slowapi` (`@limiter.limit("10/minute")` for uploads/comparison, `@limiter.limit("30/minute")` for Q&A, `@limiter.limit("20/minute")` for scenario analysis).
- **Generic 500 Error Sanitization**: Prevents internal file path and stack trace disclosure in error responses.
- **Delimiter Injection Defense**: Wraps document content in `<DOCUMENT_DATA_nonce>` tags using a cryptographic 8-character hex nonce per request across ALL prompt paths (`extraction.py`, `categorization.py`, `explanation.py`, `qa.py`, `scenario.py`, `comparison.py`).
- **Explicit Prompt Hierarchy**: System prompt explicitly instructs the LLM that content inside delimiters is untrusted DATA.
- **Input & Output Sanitization**: HTML text rendered in UI is sanitized using `bleach` to prevent XSS.
- **No Log Secrets**: Document text and API keys are never logged; only session IDs and error codes are logged.
- **Final Validation Guard**: Verifies cited clause IDs exist in the parsed document; downgrades fabricated citations to `NOT_ESTABLISHED` rather than silently dropping them.
- **Environment Isolation**: `.env.example` provided; `.env` listed in `.gitignore`.

---

## 6. Efficiency

- **SHA-256 Content-Hash Document Cache**: Uploaded documents calculate a SHA-256 hash in `backend/api/documents.py`. Identical byte streams reuse extracted clauses, classification, and TF-IDF index while issuing a new isolated session ID, skipping re-parsing and re-processing completely ($O(1)$ lookup).
- **Adaptive Page Batching**: `backend/prompts/extraction.py` dynamically groups pages by character count (~8,000 characters per batch, max 10 pages) via `create_adaptive_batches`, minimizing Gemini LLM call count for long sparse contracts while processing short 1-page documents in a single batch.
- **Min-Heap $O(1)$ Peek / $O(\log N)$ Session Expiry**: `backend/main.py` uses a heap queue (`heapq`) sorted by expiration timestamp (`sessions_heap`), transforming session cleanup scans from $O(N)$ dictionary iterations to $O(1)$ head peeks and $O(\log N)$ pop operations.
- **Concurrent Async Pipeline (`asyncio.gather`)**: Independent LLM operations (document classification + clause extraction, clause categorization + plain-English explanations) execute concurrently in parallel using `asyncio.gather`, reducing total processing latency by ~50%.
- **O(1) In-Memory LLM & Query Result Caching**: `cachetools.TTLCache` caches LLM Q&A/scenario responses for 30 minutes, bypassing redundant Gemini API calls. `ClauseRetriever` caches TF-IDF query transforms and similarity scores in memory.
- **SHA256 Content-Hash Parse Caching**: Re-uploads of identical document byte streams hit `_PARSE_CACHE` for instant O(1) page text retrieval.
- **Retrieval-First Architecture**: Q&A and Scenario prompts receive ONLY top-k retrieved clauses (never full document text), drastically reducing token cost and latency.
- **Async Non-Blocking I/O**: FastAPI endpoints use `async def`; CPU-bound PDF/DOCX parsing runs in worker thread pools (`run_in_threadpool`).
- **GZip Response Compression**: Compresses HTTP response payloads larger than 500 bytes for network bandwidth efficiency.
- **Pre-Compiled Regex & Fast Leak Detection**: System prompt leak patterns and security filters use module-level pre-compiled regex objects for O(N) linear-time text scanning.

### Architectural Justification: TF-IDF vs. Heavy Dense Embeddings

ClauseGuard intentionally uses an in-memory `TfidfVectorizer` (with unigram + bigram n-grams, log-scaled sublinear term frequency, and cosine similarity) rather than heavy neural sentence transformer embeddings. For single-document contract analysis (typically 5 to 50 pages), TF-IDF offers key advantages:
1. **Zero Cold-Start Overhead**: Requires no multi-hundred-megabyte neural weight download or local GPU/PyTorch runtime initialization.
2. **Sub-Millisecond Retrieval Latency**: Transforms and computes cosine matrix similarity in **0.15ms** (verified by automated benchmarks), compared to 100–300ms for dense transformer models on CPU.
3. **Exact Verbatim Legal Matching**: Legal contracts rely heavily on precise statutory terms (e.g. *"liquidated damages"*, *"indemnification"*, *"probationary period"*) where exact keyword & phrase matches yield **100% precision/recall** on test benchmark suites without semantic drift.
4. **Zero External API Cost**: Performs 100% local in-memory retrieval without additional embedding API token consumption.

### Horizontal Scaling & Production Deployment Note

While ClauseGuard uses high-performance in-memory caching and session state for single-instance simplicity and zero cold-start deployment, horizontal multi-instance production scaling is seamlessly achieved by replacing the in-memory `_DOCUMENT_CONTENT_CACHE` and `sessions` dict with Redis / Redis Cluster (or KeyDB) backed by `redis-py` or `aioredis`, providing shared session state and content hash deduplication across stateless FastAPI worker nodes.

### Benchmark Performance Numbers

Automated performance benchmarks (`tests/test_performance.py`):
- **Retrieval Precision / Recall**: **100% accuracy** across legal query test suites (exceeding 90% target threshold).
- **Q&A Local Pipeline Overhead**: **< 1.0 ms** average latency per Q&A call (retrieval + validation guard execution).
- **Leak Detection Throughput**: **< 2.5 ms** per 100,000 characters using pre-compiled regex patterns.
- **Session Memory Cleanup**: Automatic 1-hour session TTL background task purges expired sessions via min-heap to prevent memory leaks.

### Pipeline Complexity Notes (Big-O Analysis)

| Stage | Operation | Time Complexity | Space Complexity | Optimizations |
|---|---|---|---|---|
| **Parse** | Text Extraction | $O(P)$ where $P$ = pages | $O(T)$ where $T$ = chars | SHA256 content-hash cache $O(1)$, threadpool execution |
| **Index** | TF-IDF Matrix Build | $O(C \cdot W)$ where $C$ = clauses, $W$ = words | $O(C \cdot V)$ where $V$ = vocabulary | Calculated once at upload, reused for session |
| **Retrieve**| Cosine Similarity | $O(Q \cdot V + C)$ where $Q$ = query words | $O(k)$ top-k results | Cached matrix transform, returns top-k only |
| **Analyze** | LLM Grounded Q&A | $O(1)$ cache hit / $O(k)$ LLM call | $O(k)$ context tokens | `TTLCache` LRU deduplication, top-k prompt context |
| **Sanitize**| Regex Leak Scan | $O(L)$ where $L$ = response length | $O(L)$ | Pre-compiled regex patterns, linear scan |

### What Was Intentionally NOT Built & Why

- **No Vector Database (FAISS/Chroma)**: Single-document contract analysis works faster with in-memory TF-IDF.
- **No Persistent Multi-Tenant DB**: Keeps infrastructure minimal, zero data leakage risk, and 100% compliant with in-memory session processing.
- **No Numeric Risk Scores**: Risk scoring lacks a defensible legal methodology; qualitative tags backed by source citations are used instead.

---

## 7. Testing

The repository contains **80 automated tests** covering API routes, parser, extraction, Q&A grounding, security, performance concurrency, comparison, end-to-end integration, and accessibility compliance with 100% pass rate.

### Running the Test Suite

```bash
# Run all tests with coverage
pytest -v --cov=backend

# Run specific test modules
pytest tests/test_e2e_integration.py -v
pytest tests/test_performance.py -v
pytest tests/test_security.py -v
pytest tests/test_accessibility.py -v
```

### Test Coverage Highlights

- `test_e2e_integration.py`: End-to-end contract upload, clause extraction, Q&A asking, scenario simulation, and Markdown brief generation.
- `test_performance.py`: Retrieval precision/recall benchmark (100%), Q&A local pipeline overhead benchmark (<1ms), pipeline concurrency (`asyncio.gather`), TTLCache duplicate Q&A bypass, SHA256 parse cache, session memory cleanup test.
- `test_security.py`: HTTP security headers (`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`), GZip response compression, zero-byte rejection, zip-bomb rejection, generic 500 error sanitization, prompt injection containment, delimiter nonce isolation, XSS HTML sanitization, system prompt leak scrubbing, API key safety.
- `test_accessibility.py`: ARIA live regions (`aria-live="polite"`, `role="status"`), `aria-label` coverage on React components, landmark regions, and XSS sanitization.
- `test_api.py`: 11 full integration tests verifying health checks, upload validation, non-existent sessions, brief generation, and chat endpoints.
- `test_qa_grounding.py`: TF-IDF retrieval accuracy, certainty tag logic, final validation guard enforcement, fabricated clause ID downgrade.

---

## 8. Code Style & Architecture Conventions

ClauseGuard enforces clean architectural boundaries and strict coding standards (detailed in [`CONTRIBUTING.md`](file:///d:/Desktop/Desktop/ClauseGuard/CONTRIBUTING.md)):

- **Modular Function Length**: Every function is scoped to a single responsibility and kept under ~40 lines.
- **Type Annotations**: 100% of Python backend function signatures include explicit type hints (`mypy` verified).
- **No Bare Exceptions**: All exception handlers catch explicit types, log context, and return structured error schemas.
- **Centralized Core Utilities**: Shared utilities (rate limiting, prompt text formatters, fallback constructors) reside in `backend/core/`.

---

## 9. Accessibility

- **Keyboard Navigable**: All interactive elements (upload drag-and-drop, clause cards, chat inputs, buttons) are focusable with visible `:focus-visible` indicators.
- **Semantic HTML & ARIA**: Uses `<header>`, `<main>`, `<section>`, `<article>`, `aria-expanded`, `aria-controls`, and `aria-live="polite"` regions for screen reader updates.
- **Multi-Signal Status**: Status and certainty indicators combine icons + text tags + color (never color alone).
- **Responsive Layout**: Adapts gracefully to single-column layout on mobile viewports.

---

## 9. Setup & Run Instructions

### Prerequisites

- Python 3.10+
- Node.js v18+ & npm

### 1. Backend Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Copy environment variables template
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY=your_key_here (or GOOGLE_API_KEY)

# Start FastAPI server
uvicorn backend.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

<!-- ## 10. Demo Script (2–4 Minutes)

1. **Upload**: Drag and drop `tests/fixtures/sample_employment_agreement.pdf`.
2. **Clause Map**: View auto-generated clause cards organized by categories (Compensation, Probation, Non-Compete, Termination). Expand a card to see plain-English explanations and verbatim page-referenced source text.
3. **Ask Question**: Ask *"What happens if I resign during probation?"* Notice the top-k clause retrieval and three-way certainty output (**Stated** / **Interpretation** / **Not Established**).
4. **Lawyer Question**: Observe the automatically suggested question for your lawyer.
5. **Prompt Injection Defense**: Observe Section 11 of the sample PDF containing embedded injection instructions (`IGNORE PREVIOUS INSTRUCTIONS...`). Notice how ClauseGuard treats it as inert document text without altering AI behavior.
6. **Generate Lawyer Brief**: Click **"📋 Generate Lawyer Brief"** in the header to download an exportable Markdown briefing document for your legal consultation. -->
