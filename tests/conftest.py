"""Shared test fixtures and configuration for ClauseGuard tests."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture
def sample_pdf_bytes():
    """Load the sample employment agreement PDF fixture."""
    path = os.path.join(FIXTURES_DIR, "sample_employment_agreement.pdf")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def sample_pdf_v2_bytes():
    """Load the modified employment agreement PDF fixture."""
    path = os.path.join(FIXTURES_DIR, "sample_employment_agreement_v2.pdf")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def corrupted_pdf_bytes():
    """Load the corrupted PDF fixture."""
    path = os.path.join(FIXTURES_DIR, "sample_corrupted.pdf")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def wrong_type_bytes():
    """Load the wrong file type fixture."""
    path = os.path.join(FIXTURES_DIR, "sample.txt")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def sample_docx_bytes():
    """Load the sample service agreement DOCX fixture."""
    path = os.path.join(FIXTURES_DIR, "sample_service_agreement.docx")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def sample_clauses():
    """Create a list of sample Clause objects for testing."""
    from backend.models.schemas import Clause, ClauseCategory
    return [
        Clause(
            id="clause_000",
            section="Position and Duties",
            page=1,
            text="The Employee shall serve as Senior Software Engineer, reporting to the VP of Engineering.",
            category=ClauseCategory.OBLIGATIONS,
            plain_explanation="You will work as a Senior Software Engineer and report to the VP of Engineering.",
        ),
        Clause(
            id="clause_001",
            section="Compensation",
            page=1,
            text="The Company shall pay the Employee an annual base salary of $120,000, payable in bi-weekly installments.",
            category=ClauseCategory.COMPENSATION,
            plain_explanation="Your annual salary is $120,000 paid every two weeks.",
        ),
        Clause(
            id="clause_002",
            section="Probation Period",
            page=1,
            text="The first six (6) months of employment shall constitute a probationary period. During the probationary period, either party may terminate this Agreement with two (2) weeks written notice.",
            category=ClauseCategory.PROBATION,
            plain_explanation="You have a 6-month probation. During this time, either side can end the agreement with 2 weeks notice.",
        ),
        Clause(
            id="clause_003",
            section="Termination",
            page=2,
            text="After the probationary period, either party may terminate this Agreement by providing thirty (30) days written notice.",
            category=ClauseCategory.TERMINATION,
            plain_explanation="After probation, 30 days notice is required to end the agreement.",
        ),
        Clause(
            id="clause_004",
            section="Non-Compete",
            page=2,
            text="For a period of twelve (12) months following termination, the Employee shall not directly or indirectly engage in any business that competes with the Company within a fifty (50) mile radius.",
            category=ClauseCategory.NON_COMPETE,
            plain_explanation="After leaving, you can't work for a competitor within 50 miles for 12 months.",
        ),
        Clause(
            id="clause_005",
            section="Confidentiality",
            page=2,
            text="The Employee agrees to maintain strict confidentiality of all proprietary information, trade secrets, and business strategies.",
            category=ClauseCategory.CONFIDENTIALITY,
            plain_explanation="You must keep all company secrets and strategies confidential.",
        ),
    ]
