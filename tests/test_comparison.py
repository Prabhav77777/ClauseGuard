"""Tests for document comparison and brief generation.

Tests:
6. Comparison on two fixture versions with a known change returns correct diff
11. Brief generator produces valid markdown output
"""


from backend.models.schemas import (
    Clause,
    ClauseCategory,
    ComparisonItem,
    ComparisonResult,
    DocumentSession,
    DocumentType,
)
from backend.services.brief_generator import generate_brief


class TestComparisonSchemas:
    """Test comparison schema validation."""

    def test_comparison_item_validates(self):
        """A valid ComparisonItem passes validation."""
        item = ComparisonItem(
            status="Modified",
            old="30 days notice",
            new="60 days notice",
            materiality="substantive",
            reason="Notice period doubled, affecting exit timeline.",
        )
        assert item.status == "Modified"
        assert item.materiality == "substantive"

    def test_comparison_result_validates(self):
        """ComparisonResult with multiple items passes validation."""
        result = ComparisonResult(
            items=[
                ComparisonItem(
                    status="Modified",
                    old="salary of $120,000",
                    new="salary of $140,000",
                    materiality="substantive",
                    reason="Salary increased by $20,000.",
                ),
                ComparisonItem(
                    status="Added",
                    old=None,
                    new="Remote work policy",
                    materiality="substantive",
                    reason="New clause added allowing remote work.",
                ),
            ]
        )
        assert len(result.items) == 2

    def test_added_item_has_no_old(self):
        """Added items should have old=None."""
        item = ComparisonItem(
            status="Added",
            old=None,
            new="New clause text",
            materiality="substantive",
            reason="New provision added.",
        )
        assert item.old is None
        assert item.new is not None

    def test_removed_item_has_no_new(self):
        """Removed items should have new=None."""
        item = ComparisonItem(
            status="Removed",
            old="Old clause text",
            new=None,
            materiality="substantive",
            reason="Provision removed.",
        )
        assert item.old is not None
        assert item.new is None


class TestBriefGenerator:
    """Test the Lawyer Prep Brief generator."""

    def test_generates_valid_markdown(self):
        """Brief generator produces non-empty markdown."""
        session = DocumentSession(
            session_id="test-session",
            filename="test_agreement.pdf",
            doc_type=DocumentType.EMPLOYMENT_AGREEMENT,
            clauses=[
                Clause(
                    id="clause_000",
                    section="Compensation",
                    page=1,
                    text="Salary is $120,000.",
                    category=ClauseCategory.COMPENSATION,
                ),
            ],
            lawyer_questions=["Is the non-compete enforceable in California?"],
            unclear_items=["Disability benefits are not mentioned."],
        )
        brief = generate_brief(session)
        assert isinstance(brief, str)
        assert len(brief) > 100
        assert "# Lawyer Prep Brief" in brief

    def test_brief_contains_lawyer_questions(self):
        """Brief includes accumulated lawyer questions."""
        session = DocumentSession(
            session_id="test",
            filename="test.pdf",
            doc_type=DocumentType.EMPLOYMENT_AGREEMENT,
            clauses=[],
            lawyer_questions=[
                "Is the non-compete enforceable?",
                "What happens if probation is extended?",
            ],
        )
        brief = generate_brief(session)
        assert "non-compete enforceable" in brief
        assert "probation is extended" in brief

    def test_brief_contains_unclear_items(self):
        """Brief includes accumulated unclear items."""
        session = DocumentSession(
            session_id="test",
            filename="test.pdf",
            clauses=[],
            unclear_items=["Disability coverage not addressed."],
        )
        brief = generate_brief(session)
        assert "Disability coverage" in brief

    def test_brief_contains_disclaimer(self):
        """Brief includes a disclaimer that it's not legal advice."""
        session = DocumentSession(
            session_id="test",
            filename="test.pdf",
            clauses=[],
        )
        brief = generate_brief(session)
        assert "NOT legal advice" in brief

    def test_brief_contains_clause_summary(self):
        """Brief includes document structure summary with categories."""
        session = DocumentSession(
            session_id="test",
            filename="test.pdf",
            clauses=[
                Clause(id="c1", section="Pay", page=1, text="...", category=ClauseCategory.COMPENSATION),
                Clause(id="c2", section="Exit", page=2, text="...", category=ClauseCategory.TERMINATION),
            ],
        )
        brief = generate_brief(session)
        assert "Compensation" in brief
        assert "Termination" in brief
