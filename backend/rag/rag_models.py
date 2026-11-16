"""Pydantic schemas and contracts for Evidence-Grounded Financial RAG.

Defines schemas for research questions, retrieved evidence units, deterministic
calculation receipts, citation mappings, and structured RAG answers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    """Query payload for asking a financial research question with grounding."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language corporate finance or statutory disclosure question",
    )
    ticker: str | None = Field(
        default=None,
        description="Optional target company ticker symbol (e.g. 'AAPL')",
    )
    filing_type: str | None = Field(
        default=None,
        description="Optional statutory SEC filing type filter (e.g. '10-K', '10-Q')",
    )
    section_identifier: str | None = Field(
        default=None,
        description="Optional canonical section filter (e.g. 'ITEM_1A', 'ITEM_7')",
    )
    accession_number: str | None = Field(
        default=None,
        description="Optional specific SEC accession number filter",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of evidence passages to assemble into generation context",
    )
    use_reranker: bool = Field(
        default=True,
        description="Whether to execute cross-encoder reranking over hybrid search candidates",
    )
    include_calculations: bool = Field(
        default=True,
        description="Whether to incorporate relevant deterministic financial calculation receipts",
    )
    response_style: Literal["concise", "detailed", "bullet_points"] = Field(
        default="detailed",
        description="Stylistic depth for generated financial synthesis",
    )


class RetrievedEvidence(BaseModel):
    """Document passage unit with full statutory provenance and relevance scores."""

    evidence_id: str = Field(
        ..., description="Stable prompt-level citation identifier (e.g. 'E1')"
    )
    chunk_id: str = Field(..., description="Underlying database chunk identifier")
    ticker: str = Field(..., description="Normalized company ticker symbol")
    company_name: str = Field(..., description="Official registered company title")
    filing_type: str = Field(..., description="Filing type (e.g. '10-K', '10-Q')")
    filing_date: str = Field(..., description="Filing submission date (YYYY-MM-DD)")
    report_date: str | None = Field(
        default=None, description="Fiscal reporting period end date"
    )
    accession_number: str = Field(..., description="SEC EDGAR accession number")
    section_identifier: str = Field(
        ..., description="Canonical section identifier (e.g. 'ITEM_1A')"
    )
    section_title: str = Field(..., description="Human-readable section title")
    chunk_text: str = Field(..., description="Verbatim raw text of the filing chunk")
    source_url: str = Field(
        ..., description="Direct URL to original filing on SEC EDGAR"
    )
    dense_score: float | None = Field(
        default=None, description="Cosine similarity score from vector search"
    )
    bm25_score: float | None = Field(
        default=None, description="BM25 lexical score from sparse search"
    )
    rrf_score: float | None = Field(
        default=None, description="Reciprocal Rank Fusion score"
    )
    reranker_score: float | None = Field(
        default=None, description="Cross-encoder relevance score"
    )
    provenance_status: str = Field(
        default="valid", description="Audit status from evidence validator"
    )


class CalculationEvidence(BaseModel):
    """Deterministic financial metric receipt incorporated into RAG context."""

    evidence_id: str = Field(
        ..., description="Stable prompt-level citation identifier (e.g. 'C1')"
    )
    calculation_id: str = Field(
        ..., description="Unique persistent calculation receipt identifier"
    )
    metric_name: str = Field(..., description="Canonical financial metric name")
    calculated_value: float = Field(
        ..., description="Deterministic numerical result computed by Python"
    )
    unit: str = Field(
        ..., description="Unit of measurement (e.g. 'percentage', 'ratio', 'USD')"
    )
    formula: str = Field(..., description="Mathematical formula applied")
    period_start: str | None = Field(
        default=None, description="Fiscal period start date"
    )
    period_end: str = Field(..., description="Fiscal period end date")
    input_observations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Source SEC XBRL observations used in formula computation",
    )
    calculation_status: str = Field(
        default="calculated", description="Execution receipt status"
    )


class Citation(BaseModel):
    """Auditable citation mapping an answer claim to verified statutory evidence."""

    citation_id: str = Field(
        ..., description="Cited evidence identifier (e.g. 'E1', 'C1')"
    )
    evidence_type: Literal["filing_passage", "calculation_receipt"] = Field(
        ...,
        description="Type of supporting evidence",
    )
    source_reference: str = Field(
        ...,
        description="Human-readable statutory citation (e.g. 'AAPL 10-K (2023-11-03) Item 1A')",
    )
    source_url: str = Field(..., description="Official SEC EDGAR archive citation link")
    excerpt: str | None = Field(
        default=None, description="Verbatim passage snippet or formula summary"
    )


class RAGAnswer(BaseModel):
    """Complete, evidence-grounded response container with citation traceability."""

    answer_id: str = Field(..., description="Unique persistent answer identifier")
    question: str = Field(..., description="Submitted research question")
    answer: str = Field(..., description="Synthesized, evidence-grounded answer text")
    answer_status: Literal[
        "answered",
        "insufficient_evidence",
        "provider_unavailable",
        "generation_failed",
        "citation_validation_failed",
        "partially_supported",
        "partially_verified",
        "verification_rejected",
    ] = Field(..., description="Grounded execution status")
    citations: list[Citation] = Field(
        default_factory=list,
        description="List of verified evidence citations supporting the answer",
    )
    retrieved_evidence: list[RetrievedEvidence] = Field(
        default_factory=list,
        description="All validated filing passages supplied in the prompt context",
    )
    calculation_evidence: list[CalculationEvidence] = Field(
        default_factory=list,
        description="All deterministic calculation receipts supplied in the prompt context",
    )
    model_name: str = Field(..., description="Active LLM model identifier")
    provider: str = Field(..., description="Active LLM provider backend")
    retrieval_method: str = Field(
        ..., description="Retrieval pipeline used ('hybrid', 'hybrid_reranked')"
    )
    generation_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="LLM execution timings, token counts, and parameters",
    )
    warnings: list[str] = Field(
        default_factory=list, description="Audit, provenance, or context warnings"
    )
    verification_run_id: str | None = Field(
        default=None,
        description="Associated claim-level verification run identifier",
    )
    verification_status: str | None = Field(
        default=None,
        description="Aggregate claim verification outcome ('verified', 'partially_verified', 'rejected')",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 generation timestamp",
    )


class RAGCapabilitiesResponse(BaseModel):
    """Diagnostics exposing active RAG system capabilities and provider readiness."""

    supported_retrieval_modes: list[str] = Field(
        default_factory=lambda: ["dense", "sparse", "hybrid", "hybrid_reranked"],
        description="Supported information retrieval pipelines",
    )
    reranker_available: bool = Field(
        ..., description="Whether cross-encoder reranker is ready"
    )
    reranker_model: str = Field(..., description="Active cross-encoder model name")
    calculation_engine_enabled: bool = Field(
        ..., description="Whether deterministic calculation integration is active"
    )
    citation_verification_enabled: bool = Field(
        ..., description="Whether citation validation is active"
    )
    llm_provider: str = Field(..., description="Configured LLM provider")
    llm_model: str = Field(..., description="Configured LLM model identifier")
    llm_online: bool = Field(
        ..., description="Whether LLM provider is currently reachable"
    )
    verification_engine_enabled: bool = Field(
        default=True,
        description="Whether claim-level verification is active",
    )
    verification_version: str = Field(
        default="0.1.0",
        description="Verification engine version",
    )
