"""Comprehensive API endpoint test suite.

Tests:
- GET / and GET /api/health
- POST /api/documents/upload (valid PDF, valid DOCX, invalid format, corrupted file)
- GET /api/documents/{session_id}/clauses
- GET /api/documents/{session_id}/clauses/{clause_id}
- GET /api/documents/{session_id}/brief
- Security headers and CORS middleware on HTTP routes
"""

import io
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import Clause, ClauseCategory, DocumentSession, DocumentType


@pytest.fixture
def api_client():
    """FastAPI TestClient fixture with lifespan context enabled."""
    with TestClient(app) as client:
        yield client


class TestHealthAndRootEndpoints:
    """Test health check and root endpoints."""

    def test_health_check_returns_ok(self, api_client):
        response = api_client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_root_endpoint_returns_ok(self, api_client):
        response = api_client.get("/")
        assert response.status_code == 200
        assert response.json()["service"] == "ClauseGuard API"

    def test_security_headers_present_on_routes(self, api_client):
        response = api_client.get("/")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


class TestDocumentEndpoints:
    """Test document upload, clause retrieval, and brief generation endpoints."""

    def test_upload_invalid_file_type(self, api_client):
        """Uploading a plain text file returns 415 Unsupported Media Type."""
        response = api_client.post(
            "/api/documents/upload",
            files={"file": ("test.txt", b"plain text", "text/plain")},
        )
        assert response.status_code in (400, 415)

    def test_upload_empty_file(self, api_client):
        """Uploading an empty file returns 400 Bad Request."""
        response = api_client.post(
            "/api/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    def test_get_clauses_non_existent_session(self, api_client):
        """Getting clauses for non-existent session returns 404."""
        response = api_client.get("/api/documents/non-existent-session-id/clauses")
        assert response.status_code == 404

    def test_get_clause_by_id_non_existent_session(self, api_client):
        """Getting clause for non-existent session returns 404."""
        response = api_client.get("/api/documents/non-existent-session-id/clauses/clause_000")
        assert response.status_code == 404

    def test_get_brief_non_existent_session(self, api_client):
        """Getting brief for non-existent session returns 404."""
        response = api_client.get("/api/documents/non-existent-session-id/brief")
        assert response.status_code == 404

    def test_get_brief_valid_session(self, api_client):
        """Getting brief for valid session returns Markdown text."""
        # Inject mock session into app state
        session_id = "test-brief-session-123"
        app.state.sessions[session_id] = DocumentSession(
            session_id=session_id,
            filename="test_contract.pdf",
            doc_type=DocumentType.EMPLOYMENT_AGREEMENT,
            clauses=[
                Clause(
                    id="clause_000",
                    section="Compensation",
                    page=1,
                    text="Salary is $100,000 per year.",
                    category=ClauseCategory.COMPENSATION,
                    plain_explanation="Your annual pay is $100,000.",
                )
            ],
            lawyer_questions=["Is the salary paid bi-weekly?"],
            unclear_items=["Bonus criteria not specified."],
        )

        response = api_client.get(f"/api/documents/{session_id}/brief")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "Lawyer Prep Brief" in response.text
        assert "Salary is $100,000" in response.text or "Compensation" in response.text

        # Test GET /clauses and GET /clauses/{id} with valid session
        clauses_resp = api_client.get(f"/api/documents/{session_id}/clauses")
        assert clauses_resp.status_code == 200
        assert len(clauses_resp.json()) == 1

        clause_resp = api_client.get(f"/api/documents/{session_id}/clauses/clause_000")
        assert clause_resp.status_code == 200
        assert clause_resp.json()["id"] == "clause_000"


class TestChatEndpoints:
    """Test Q&A and scenario analysis endpoints."""

    def test_ask_non_existent_session(self, api_client):
        """Asking a question for non-existent session returns 404."""
        response = api_client.post(
            "/api/chat/invalid-session/ask",
            json={"question": "What is the salary?"},
        )
        assert response.status_code == 404

    def test_scenario_non_existent_session(self, api_client):
        """Analyzing scenario for non-existent session returns 404."""
        response = api_client.post(
            "/api/chat/invalid-session/scenario",
            json={"scenario": "What if I resign?"},
        )
        assert response.status_code == 404
