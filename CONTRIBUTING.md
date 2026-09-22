# Contributing to ClauseGuard

Thank you for contributing to **ClauseGuard**! To maintain code quality, security, and performance standards across the codebase, please adhere to the guidelines below.

---

## Code Style & Standards

### Python (Backend)
- **Python Version**: Target Python 3.10+.
- **Type Hints**: All function signatures must include explicit type annotations (e.g. `def process(text: str) -> list[str]:`).
- **Function Length**: Keep functions modular and single-responsibility — maximum ~40 lines per function.
- **Docstrings**: Every module, class, and function must have concise Google/Sphinx style docstrings explaining its purpose and return values.
- **Exception Handling**: Never use bare `except:`. Catch explicit exceptions (e.g., `HTTPException`, `ValueError`), log the error with context, and return structured error responses.
- **Linting & Formatting**: Enforced via `ruff check .` and `mypy backend/`.

### React (Frontend)
- **Component Design**: Functional components using React Hooks (`useState`, `useCallback`, `useMemo`).
- **Accessibility (a11y)**:
  - All interactive controls (buttons, links, inputs) must be keyboard navigable (`tabIndex={0}`, visible `:focus-visible` styling).
  - Icon-only buttons must have an explicit `aria-label`.
  - Dynamic status changes must use semantic `role="status"` or `role="log"` with `aria-live="polite"`.
- **CSS Variable Design Tokens**: Use standard CSS variables defined in `src/index.css` (never hardcode arbitrary hex colors or static offsets).

---

## Architecture & Module Boundaries

- `backend/api/`: FastAPI route handlers (request parsing, session lookups, response formatting).
- `backend/security/`: Security controls (magic byte file validation, zip-bomb protection, prompt injection nonces, HTML sanitization).
- `backend/services/`: Core legal analysis orchestration (document parsing, TF-IDF retrieval, brief generation).
- `backend/prompts/`: Single-purpose Gemini LLM prompt modules using structured Pydantic schemas.
- `backend/core/`: Shared helper functions and utility definitions.
- `frontend/src/components/`: Reusable React UI components (ClauseMap, ChatPanel, BriefExport).

---

## Testing & Quality Gate

Before submitting changes, verify that the automated test suite and linters pass cleanly:

```bash
# Run pytest test suite with coverage
pytest -v --cov=backend

# Run ruff linter
ruff check .

# Run mypy static type checking
mypy backend/
```
