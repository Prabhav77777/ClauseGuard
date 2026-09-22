"""
MODULE: Central Pydantic schemas and Enum taxonomies for structured LLM inputs/outputs and API responses.

@level-one-validation: Schemas strictly enforce runtime data types and Pydantic field constraints across all backend layers. Tested extensively in test_extraction.py, test_qa_grounding.py, and test_comparison.py.

#Scope-Of-Improvement: Add custom Pydantic validators to enforce non-empty whitespace checking on verbatim clause strings.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# #Business-Intent: Fixed 15-category taxonomy ensuring deterministic categorization without hallucinated category strings.
class ClauseCategory(str, Enum):
    """Fixed taxonomy for clause categorization. LLM must select from this enum only."""
    COMPENSATION = "compensation"
    TERMINATION = "termination"
    NOTICE_PERIOD = "notice_period"
    PROBATION = "probation"
    NON_COMPETE = "non_compete"
    CONFIDENTIALITY = "confidentiality"
    LIABILITY = "liability"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DISPUTE_RESOLUTION = "dispute_resolution"
    GOVERNING_LAW = "governing_law"
    BENEFITS = "benefits"
    OBLIGATIONS = "obligations"
    RESTRICTIONS = "restrictions"
    INDEMNIFICATION = "indemnification"
    GENERAL = "general"


class DocumentType(str, Enum):
    """Supported document type classifications."""
    EMPLOYMENT_AGREEMENT = "employment_agreement"
    LEASE_AGREEMENT = "lease_agreement"
    SERVICE_AGREEMENT = "service_agreement"
    NDA = "nda"
    PARTNERSHIP_AGREEMENT = "partnership_agreement"
    UNKNOWN = "unknown"


# #Business-Intent: Enforces strict three-way certainty distinction (stated/interpreted/not_established) to prevent AI legal conclusions.
class CertaintyLevel(str, Enum):
    """Three-way certainty distinction for QA responses.

    Every substantive answer must be tagged with one of:
    - STATED: The document explicitly says this
    - INTERPRETED: A reasonable inference from the document
    - NOT_ESTABLISHED: Cannot be determined from the document
    """
    STATED = "stated"
    INTERPRETED = "interpreted"
    NOT_ESTABLISHED = "not_established"


# --- Document Parsing ---

class PageText(BaseModel):
    """Raw text extracted from a single page of a document."""
    page_number: int = Field(..., description="1-indexed page number")
    text: str = Field(..., description="Raw text content of the page")


class Clause(BaseModel):
    """A single clause extracted from a legal document.

    The `text` field contains the VERBATIM text from the document,
    never paraphrased, to ensure verifiability by string match.
    """
    id: str = Field(..., description="Unique clause identifier, e.g. 'clause_001'")
    section: str = Field(..., description="Section heading or title")
    page: int = Field(..., description="Source page number (1-indexed)")
    text: str = Field(..., description="Verbatim clause text from the document")
    category: Optional[ClauseCategory] = Field(None, description="Clause category from fixed taxonomy")
    plain_explanation: Optional[str] = Field(None, description="Plain-English explanation")


# --- LLM Response Schemas ---

class ClassificationResult(BaseModel):
    """Document type classification output."""
    doc_type: DocumentType = Field(..., description="Classified document type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence 0.0-1.0")


class ExtractionResult(BaseModel):
    """Clause extraction output from the LLM."""
    clauses: list[Clause] = Field(..., description="Extracted clauses with verbatim text")


class CategorizationResult(BaseModel):
    """Single clause categorization result."""
    clause_id: str = Field(..., description="ID of the categorized clause")
    category: ClauseCategory = Field(..., description="Assigned category from fixed taxonomy")


class BatchCategorizationResult(BaseModel):
    """Batch categorization results for multiple clauses."""
    categorizations: list[CategorizationResult] = Field(..., description="Category assignments")


class PlainExplanationResult(BaseModel):
    """Plain-language explanation of a single clause."""
    clause_id: str = Field(..., description="ID of the explained clause")
    plain_explanation: str = Field(..., description="Plain-English explanation that adds no facts absent from the clause")


class BatchExplanationResult(BaseModel):
    """Batch explanation results for multiple clauses."""
    explanations: list[PlainExplanationResult] = Field(..., description="Plain-language explanations")


class QAResponse(BaseModel):
    """Evidence-grounded Q&A response with three-way distinction.

    Every answer must explicitly separate:
    1. What the document explicitly states
    2. What is a reasonable interpretation
    3. What cannot be determined from the document
    """
    answer: str = Field(..., description="Complete answer to the user's question")
    sources: list[str] = Field(..., description="Clause IDs cited in the answer")
    certainty: CertaintyLevel = Field(..., description="Overall certainty level")
    stated: str = Field(..., description="What the document explicitly says about this topic")
    interpreted: str = Field(..., description="Reasonable interpretation beyond literal text")
    not_established: str = Field(..., description="What cannot be determined from the document")
    lawyer_question: Optional[str] = Field(None, description="Suggested question for a lawyer")


class ScenarioResponse(BaseModel):
    """Scenario analysis response — implications labeled as interpretation, never legal conclusions."""
    relevant_clauses: list[str] = Field(..., description="Clause IDs relevant to the scenario")
    what_document_says: str = Field(..., description="What the document explicitly states about this scenario")
    potential_implication: str = Field(..., description="Reasonable interpretation (labeled as such, not a legal conclusion)")
    unclear: str = Field(..., description="What remains unclear or undetermined")
    lawyer_question: str = Field(..., description="Suggested question for a lawyer about this scenario")


class ComparisonItem(BaseModel):
    """Single clause comparison result between two documents."""
    status: str = Field(..., description="Change status: Added, Removed, or Modified")
    old: Optional[str] = Field(None, description="Original clause text (None if Added)")
    new: Optional[str] = Field(None, description="New clause text (None if Removed)")
    materiality: str = Field(..., description="'cosmetic' or 'substantive'")
    reason: str = Field(..., description="Justification for the materiality classification")


class ComparisonResult(BaseModel):
    """Full comparison result between two documents."""
    items: list[ComparisonItem] = Field(..., description="Individual clause comparisons")


class InconsistencyResult(BaseModel):
    """Detected inconsistency between clauses in the same document."""
    clause_ids: list[str] = Field(..., description="IDs of the inconsistent clauses")
    description: str = Field(..., description="Description of the inconsistency")


class InconsistencyReport(BaseModel):
    """Container schema for structured LLM response listing clause inconsistencies."""
    inconsistencies: list[InconsistencyResult] = Field(default_factory=list, description="List of detected clause inconsistencies")


class ValidationResult(BaseModel):
    """Uncertainty validation — binary check on whether an answer is supported."""
    is_supported: bool = Field(..., description="Whether the answer is supported by the source clauses")
    notes: str = Field(..., description="Explanation of the validation result")


class FinalValidationResult(BaseModel):
    """Final response validation — acts as the guard on QA/scenario outputs.

    Unsupported claims get downgraded to 'not established', never silently deleted.
    Strips anything resembling a leaked system prompt.
    """
    passed: bool = Field(..., description="Whether the response passed validation")
    corrected_response: Optional[dict] = Field(None, description="Corrected response if validation failed")


# --- Session State ---

# #Business-Intent: Defines DocumentSession state schema including last_accessed timestamp for O(1) heap expiry.
class DocumentSession(BaseModel):
    """In-memory session state for a processed document."""
    session_id: str = Field(..., description="Unique session identifier")
    filename: str = Field("", description="Original filename")
    doc_type: Optional[DocumentType] = Field(None, description="Classified document type")
    clauses: list[Clause] = Field(default_factory=list, description="Extracted and categorized clauses")
    raw_pages: list[PageText] = Field(default_factory=list, description="Page-indexed raw text")
    unclear_items: list[str] = Field(default_factory=list, description="Accumulated unclear items for lawyer brief")
    lawyer_questions: list[str] = Field(default_factory=list, description="Accumulated lawyer questions")
    last_accessed: float = Field(default_factory=time.time, description="Timestamp of last activity in seconds")
    inconsistencies: Optional[list[InconsistencyResult]] = Field(default=None, description="Lazy-cached inconsistency analysis result")


# --- API Request/Response ---

class UploadResponse(BaseModel):
    """Response from document upload endpoint."""
    session_id: str
    filename: str
    doc_type: Optional[DocumentType]
    total_pages: int
    total_clauses: int
    clauses: list[Clause]


class AskRequest(BaseModel):
    """Request body for the Q&A endpoint."""
    question: str = Field(..., min_length=1, max_length=2000, description="User's question about the document")


class ScenarioRequest(BaseModel):
    """Request body for the scenario analysis endpoint."""
    scenario: str = Field(..., min_length=1, max_length=2000, description="Scenario description, e.g. 'What happens if I resign after 4 months?'")


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")
