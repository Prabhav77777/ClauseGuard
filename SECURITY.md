# Security Policy & Architecture Documentation

> **ClauseGuard Security Principles**: Defense in depth, strict prompt/data boundary isolation, input/output sanitization, magic byte file validation, and zero log credential leakage.

---

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | :white_check_mark: |

---

## Reporting a Vulnerability

If you discover a potential security vulnerability in ClauseGuard, please report it via private channel to `security@clauseguard.app` or file a private GitHub Security Advisory. We acknowledge all reports within 24 hours.

---

## Security Architecture & Defenses Implemented

### 1. Prompt Injection & Boundary Isolation (`backend/security/prompt_guard.py`)
- **Nonce-Tagged DATA Delimiters**: All document text passed to LLM prompts is wrapped in cryptographic `<DOCUMENT_DATA_nonce>` delimiters using an 8-character hex nonce generated per request.
- **Explicit Prompt Hierarchy**: System prompts explicitly instruct the model that content inside delimiters is untrusted DATA and must never alter system instructions or role parameters.
- **System Prompt Leak scrubbing**: Pre-compiled regex patterns scan all outgoing responses for prompt leaks and strip system instructions before returning data to the client.

### 2. Binary File Validation & Zip Bomb DoS Defense (`backend/security/validation.py`)
- **Magic Byte Validation**: File signatures (`%PDF-`, `PK\x03\x04`) are checked at the binary level instead of relying on user-provided file extensions.
- **Zip Bomb & XML Blowup Guard**: DOCX files are checked for uncompressed-to-compressed size ratio (> 100:1) and total uncompressed size ceiling (> 25MB) prior to XML parsing.
- **Strict Size/Page Ceilings**: Enforces file size limits (10MB), page limits (50 pages), and character count caps (500,000 chars).

### 3. Output Sanitization & Citation Verification
- **HTML Sanitization**: All document text rendered in UI is sanitized using `bleach` to eliminate XSS vectors.
- **Clause Citation Guard**: Cited clause IDs are cross-referenced against the parsed document's clause ID set. Fabricated or un-verified citations are downgraded to `NOT_ESTABLISHED`.

### 4. Application & Transport Security (`backend/main.py`)
- **HTTP Security Response Headers**: Enforces `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin`.
- **Content Security Policy**: Enforces strict CSP header rules (`default-src 'self'`).
- **Rate Limiting**: IP-based rate limiting via `slowapi` (`10 requests/minute`).
- **Credential Protection**: Configuration classes mask API keys in string/repr outputs (`GEMINI_API_KEY='***'`).
- **Generic Error Responses**: Production 500 exception handlers return generic error details without stack traces or internal file paths.
