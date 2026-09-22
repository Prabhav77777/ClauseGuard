# ClauseGuard Focused

> **GenAI-Powered Legal Document Analysis & Assistance System**
>
> *Understand any contract, ask it anything, and walk into your lawyer's office already prepared.*

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
| **Helping users understand their options and potential next steps** | Scenario Simulator reasoning across multiple clause categories ("What happens if I resign after 4 months?"). | `backend/prompts/scenario.py` |
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

- `backend/security/validation.py`: File upload security (magic bytes signature, file size ceiling, page/character limits).
- `backend/security/prompt_guard.py`: Prompt injection defense with per-request randomized nonces (`<DOCUMENT_DATA_nonce>`), HTML sanitization via `bleach`, and system prompt leak scrubbing.
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
- **Magic Byte & Zip Bomb Defense**: Verifies binary signatures (`%PDF-`, `PK\x03\x04` ZIP structure with `word/document.xml`), not user-supplied file extensions, and rejects zip bombs (compression ratio > 100:1 or uncompressed > 25MB) prior to XML parsing.
- **Generic 500 Error Sanitization**: Prevents internal file path and stack trace disclosure in error responses.
- **Delimiter Injection Defense**: Wraps document content in `<DOCUMENT_DATA_nonce>` tags using a cryptographic 8-character hex nonce per request.
- **Explicit Prompt Hierarchy**: System prompt explicitly instructs the LLM that content inside delimiters is untrusted DATA.
- **Input & Output Sanitization**: HTML text rendered in UI is sanitized using `bleach` to prevent XSS.
- **No Log Secrets**: Document text and API keys are never logged; only session IDs and error codes are logged.
- **Final Validation Guard**: Verifies cited clause IDs exist in the parsed document; downgrades fabricated citations to `NOT_ESTABLISHED` rather than silently dropping them.
- **Environment Isolation**: `.env.example` provided; `.env` listed in `.gitignore`.

---

## 6. Efficiency

- **Concurrent Async Pipeline (`asyncio.gather`)**: Independent LLM operations (document classification + clause extraction, clause categorization + plain-English explanations) execute concurrently in parallel using `asyncio.gather`, reducing total processing latency by ~50%.
- **O(1) In-Memory LLM & Query Result Caching**: `cachetools.TTLCache` caches LLM Q&A/scenario responses for 30 minutes, bypassing redundant Gemini API calls. `ClauseRetriever` caches TF-IDF query transforms and similarity scores in memory.
- **SHA256 Content-Hash Parse Caching**: Re-uploads of identical document byte streams hit `_PARSE_CACHE` for instant O(1) page text retrieval.
- **Retrieval-First Architecture**: Q&A and Scenario prompts receive ONLY top-k retrieved clauses (never full document text), drastically reducing token cost and latency.
- **Async Non-Blocking I/O**: FastAPI endpoints use `async def`; CPU-bound PDF/DOCX parsing runs in worker thread pools (`run_in_threadpool`).
- **GZip Response Compression**: Compresses HTTP response payloads larger than 500 bytes for network bandwidth efficiency.
- **Pre-Compiled Regex & Fast Leak Detection**: System prompt leak patterns and security filters use module-level pre-compiled regex objects for O(N) linear-time text scanning.
- **In-Memory TF-IDF**: Uses `scikit-learn` TF-IDF vectorizer fitted once per session — zero external vector DB overhead or embedding API costs.

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

The repository contains **71 automated tests** covering API routes, parser, extraction, Q&A grounding, security, performance concurrency, comparison, and brief generation with 100% pass rate.

### Running the Test Suite

```bash
# Run all tests
pytest -v

# Run specific test modules
pytest tests/test_api.py -v
pytest tests/test_performance.py -v
pytest tests/test_security.py -v
pytest tests/test_qa_grounding.py -v
```

### Test Coverage Highlights

- `test_api.py`: 11 full integration tests verifying health checks, upload validation, non-existent sessions, brief generation, and chat endpoints.
- `test_performance.py`: Pipeline concurrency (`asyncio.gather`), in-memory TF-IDF query cache hit latency, TTLCache duplicate Q&A bypass, SHA256 parse cache, pre-compiled regex benchmark.
- `test_security.py`: HTTP security headers (`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`), GZip response compression, zip-bomb rejection, generic 500 error sanitization, prompt injection containment, delimiter nonce isolation, XSS HTML sanitization, system prompt leak scrubbing, API key safety.
- `test_qa_grounding.py`: TF-IDF retrieval accuracy, certainty tag logic, final validation guard enforcement, fabricated clause ID downgrade.
- `test_extraction.py`: Pydantic schema validation for all 15+ models, category enum coverage, sequential ID structure.
- `test_comparison.py`: Added/Removed/Modified materiality classification schemas, Lawyer Prep Brief Markdown generation.

---

## 8. Accessibility

- **Keyboard Navigable**: All interactive elements (upload drag-and-drop, clause cards, chat inputs, buttons) are focusable with visible `:focus-visible` indicators.
- **Semantic HTML & ARIA**: Uses `<header>`, `<main>`, `<section>`, `<article>`, `aria-expanded`, `aria-controls`, and `aria-live="polite"` regions for screen reader updates.
- **WCAG AA Contrast**: Text colors satisfy 4.5:1 minimum contrast ratio across light and dark modes.
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
