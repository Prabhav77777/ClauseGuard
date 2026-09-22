"""
Unit and integration tests for cross-clause inconsistency detection.

Verifies:
1. GET /api/documents/{session_id}/inconsistencies endpoint returns flagged inconsistencies.
2. Consistent document returns empty list.
3. InconsistencyResult schema structurally prevents returning a winning/controlling clause.
4. Inconsistency prompt instructions explicitly forbid resolving controlling provisions.
"""

import inspect
import time

from fastapi.testclient import TestClient

from backend.main import app, sessions, sessions_heap
from backend.models.schemas import Clause, DocumentSession, InconsistencyResult
from backend.prompts.inconsistency import detect_inconsistencies


class TestInconsistencyDetection:
    def test_inconsistency_endpoint_flagged_conflict(self, monkeypatch):
        """Verify endpoint returns detected inconsistencies when document contains contradictory clauses."""
        sessions.clear()
        sessions_heap.clear()

        sid = "test_inconsistency_session"
        c1 = Clause(id="clause_008", section="Section 8 - Notice", page=3, text="Either party may terminate upon 30 days notice.")
        c2 = Clause(id="clause_017", section="Section 17 - Termination", page=7, text="Termination requires 60 days written notice.")

        session = DocumentSession(
            session_id=sid,
            filename="conflicting_contract.pdf",
            clauses=[c1, c2],
            last_accessed=time.time(),
        )
        sessions[sid] = session
        app.state.sessions = sessions

        mock_inconsistencies = [
            InconsistencyResult(
                clause_ids=["clause_008", "clause_017"],
                description="Section 8 states 30 days notice is required, whereas Section 17 requires 60 days notice. The document leaves the controlling provision undetermined."
            )
        ]

        async def mock_detect_inconsistencies(clauses):
            return mock_inconsistencies

        monkeypatch.setattr("backend.api.documents.detect_inconsistencies", mock_detect_inconsistencies)

        with TestClient(app) as client:
            response = client.get(f"/api/documents/{sid}/inconsistencies")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["clause_ids"] == ["clause_008", "clause_017"]
            assert "30 days" in data[0]["description"]
            assert "60 days" in data[0]["description"]

            # Confirm result is now cached on session
            assert session.inconsistencies == mock_inconsistencies

            # Second call should return cached result without calling detect_inconsistencies again
            monkeypatch.setattr("backend.api.documents.detect_inconsistencies", None)
            res2 = client.get(f"/api/documents/{sid}/inconsistencies")
            assert res2.status_code == 200
            assert res2.json() == data

    def test_inconsistency_endpoint_no_conflicts(self, monkeypatch):
        """Verify endpoint returns empty list for consistent document."""
        sessions.clear()
        sessions_heap.clear()

        sid = "test_consistent_session"
        c1 = Clause(id="clause_001", section="Section 1", page=1, text="Consistent terms.")
        session = DocumentSession(session_id=sid, filename="clean.pdf", clauses=[c1], last_accessed=time.time())
        sessions[sid] = session
        app.state.sessions = sessions

        async def mock_detect_empty(clauses):
            return []

        monkeypatch.setattr("backend.api.documents.detect_inconsistencies", mock_detect_empty)

        with TestClient(app) as client:
            response = client.get(f"/api/documents/{sid}/inconsistencies")
            assert response.status_code == 200
            assert response.json() == []

    def test_inconsistency_schema_structural_and_prompt_guarantees(self):
        """Verify InconsistencyResult schema has no controlling/winner clause field and prompt forbids resolution."""
        # Structural assertion: InconsistencyResult model fields
        field_names = set(InconsistencyResult.model_fields.keys())
        assert field_names == {"clause_ids", "description"}, f"Unexpected fields in InconsistencyResult: {field_names}"
        assert "winning_clause" not in field_names
        assert "controlling_clause" not in field_names
        assert "resolution" not in field_names

        # Prompt inspection assertion: detect_inconsistencies source code contains anti-resolution mandate
        source_code = inspect.getsource(detect_inconsistencies)
        assert "NEVER attempt to resolve" in source_code
        assert "controlling provision undetermined" in source_code
