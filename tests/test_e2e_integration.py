"""End-to-End Integration Test Suite for ClauseGuard.

Executes complete document lifecycle:
1. Upload real sample contract PDF
2. Extract page-indexed clauses
3. Execute evidence-grounded Q&A
4. Execute multi-clause scenario simulation
5. Generate lawyer prep brief markdown
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import CertaintyLevel


class TestEndToEndContractFlow:
    """End-to-end integration tests verifying complete document analysis pipeline."""

    @pytest.mark.asyncio
    async def test_full_contract_upload_qa_scenario_flow(self, sample_pdf_bytes, monkeypatch):
        """Upload contract, ask question, run scenario, and verify clause grounding."""
        client = TestClient(app)

        # Mock LLM API calls to return structured responses with valid clause citations
        async def mock_classify(pages):
            from backend.models.schemas import ClassificationResult, DocumentType
            return ClassificationResult(doc_type=DocumentType.EMPLOYMENT_AGREEMENT, confidence=0.98)

        async def mock_extract(pages):
            from backend.models.schemas import Clause, ClauseCategory
            return [
                Clause(
                    id="clause_000",
                    section="Position and Duties",
                    page=1,
                    text="The Employee shall serve as Senior Software Engineer.",
                    category=ClauseCategory.GENERAL,
                    plain_explanation="Your job title is Senior Software Engineer."
                ),
                Clause(
                    id="clause_001",
                    section="Compensation",
                    page=1,
                    text="Base salary is $120,000 per year payable monthly.",
                    category=ClauseCategory.COMPENSATION,
                    plain_explanation="You earn $120,000 per year."
                ),
                Clause(
                    id="clause_002",
                    section="Probation Period",
                    page=1,
                    text="First 6 months constitute a probation period with 2 weeks notice.",
                    category=ClauseCategory.PROBATION,
                    plain_explanation="Probation lasts 6 months with 2 weeks notice."
                )
            ]

        async def mock_categorize(clauses):
            from backend.models.schemas import CategorizationResult, ClauseCategory
            return [
                CategorizationResult(clause_id=c.id, category=c.category or ClauseCategory.GENERAL)
                for c in clauses
            ]

        async def mock_explain(clauses):
            from backend.models.schemas import PlainExplanationResult
            return [
                PlainExplanationResult(clause_id=c.id, plain_explanation=c.plain_explanation or "")
                for c in clauses
            ]

        async def mock_qa(question, clauses):
            from backend.models.schemas import QAResponse
            return QAResponse(
                answer="Base salary is $120,000 per year.",
                sources=["clause_001"],
                certainty=CertaintyLevel.STATED,
                stated="Base salary is $120,000 per year payable monthly.",
                interpreted="",
                not_established="",
                lawyer_question="Is salary paid on fixed monthly dates?"
            )

        async def mock_scenario(scenario, clauses):
            from backend.models.schemas import ScenarioResponse
            return ScenarioResponse(
                relevant_clauses=["clause_002"],
                what_document_says="First 6 months constitute a probation period.",
                potential_implication="Based on interpretation of the clauses, 2 weeks notice is required.",
                unclear="Effect of accrued leave on notice period is unstated.",
                lawyer_question="Does accrued vacation count toward probation notice?"
            )

        monkeypatch.setattr("backend.services.clause_extractor.classify_document", mock_classify)
        monkeypatch.setattr("backend.services.clause_extractor.extract_clauses_from_pages", mock_extract)
        monkeypatch.setattr("backend.services.clause_extractor.categorize_clauses", mock_categorize)
        monkeypatch.setattr("backend.services.clause_extractor.explain_clauses", mock_explain)
        monkeypatch.setattr("backend.services.legal_analyzer.answer_question", mock_qa)
        monkeypatch.setattr("backend.services.legal_analyzer.analyze_scenario", mock_scenario)

        # 1. Upload contract PDF
        upload_res = client.post(
            "/api/documents/upload",
            files={"file": ("employment_contract.pdf", sample_pdf_bytes, "application/pdf")}
        )
        assert upload_res.status_code == 200
        upload_data = upload_res.json()
        session_id = upload_data["session_id"]
        assert len(upload_data["clauses"]) == 3
        assert upload_data["total_clauses"] == 3

        # 2. Get clauses endpoint
        clauses_res = client.get(f"/api/documents/{session_id}/clauses")
        assert clauses_res.status_code == 200
        assert len(clauses_res.json()) == 3

        # 3. Ask Q&A question
        qa_res = client.post(
            f"/api/chat/{session_id}/ask",
            json={"question": "What is my base salary?"}
        )
        assert qa_res.status_code == 200
        qa_data = qa_res.json()
        assert qa_data["sources"] == ["clause_001"]
        assert qa_data["certainty"] == "stated"
        assert "120,000" in qa_data["stated"]

        # 4. Run scenario simulator
        scenario_res = client.post(
            f"/api/chat/{session_id}/scenario",
            json={"scenario": "Can I be terminated without notice during probation?"}
        )
        assert scenario_res.status_code == 200
        scenario_data = scenario_res.json()
        assert scenario_data["relevant_clauses"] == ["clause_002"]
        assert "probation period" in scenario_data["what_document_says"]

        # 5. Generate Lawyer Brief markdown
        brief_res = client.get(f"/api/documents/{session_id}/brief")
        assert brief_res.status_code == 200
        assert brief_res.headers["content-type"].startswith("text/markdown")
        brief_text = brief_res.text
        assert "# Lawyer Prep Brief" in brief_text
        assert "clause_001" in brief_text or "clause_002" in brief_text
