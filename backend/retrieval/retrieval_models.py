"""Pydantic schemas and data models for semantic embeddings and vector retrieval.

Defines request and response contracts for document chunk indexing,
indexing status diagnostics, semantic similarity search, and vector store statistics.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IndexingRequest(BaseModel):
    """Request payload for triggering document chunk embedding generation."""

    filing_type: str | None = Field(
        default=None,
        description="Optional filter by statutory filing type (e.g. '10-K', '10-Q')",
    )
    accession_number: str | None = Field(
        default=None,
        description="Optional filter by specific SEC accession number",
    )
    force_reindex: bool = Field(
        default=False,
        description="If True, recomputes embeddings even if content hash is unchanged",
    )


class IndexingSummary(BaseModel):
    """Summary of batch embedding and vector indexing run."""

    ticker: str | None = Field(
        default=None,
        description="Target company ticker, or None if global indexing",
    )
    total_discovered: int = Field(
        ...,
        description="Total eligible chunks discovered matching criteria",
    )
    already_indexed: int = Field(
        ...,
        description="Chunks skipped because valid up-to-date embeddings exist",
    )
    newly_indexed: int = Field(
        ...,
        description="Newly embedded chunks added to vector store and database",
    )
    updated_indexed: int = Field(
        ...,
        description="Chunks re-embedded due to text change or force_reindex",
    )
    failed: int = Field(
        ...,
        description="Number of chunks that failed embedding or persistence",
    )
    model_name: str = Field(
        ...,
        description="Active pretrained sentence embedding model",
    )
    backend: str = Field(
        ...,
        description="Active vector store backend ('faiss' or 'numpy')",
    )
    embedding_dimension: int = Field(
        ...,
        description="Dimensionality of generated vector embeddings",
    )
    duration_seconds: float = Field(
        ...,
        description="Total elapsed wall-clock processing time in seconds",
    )
    message: str | None = Field(
        default=None,
        description="Descriptive status message or warning details",
    )


class EmbeddingStatusResponse(BaseModel):
    """Diagnostics detailing chunk embedding coverage for a company."""

    ticker: str = Field(..., description="Target company ticker symbol")
    total_available_chunks: int = Field(
        ...,
        description="Total document chunks stored in SQLite for this company",
    )
    indexed_chunks: int = Field(
        ...,
        description="Total chunks successfully indexed in the active vector index",
    )
    pending_chunks: int = Field(
        ...,
        description="Chunks awaiting embedding generation",
    )
    failed_chunks: int = Field(
        ...,
        description="Chunks whose last embedding attempt recorded an error",
    )
    active_model: str = Field(
        ...,
        description="Name of configured embedding model",
    )
    active_vector_backend: str = Field(
        ...,
        description="Name of active vector store backend",
    )
    embedding_dimension: int = Field(
        ...,
        description="Dimensionality of vector embeddings",
    )


class SemanticSearchRequest(BaseModel):
    """Query parameters for dense semantic similarity search over filing chunks."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language question or search query",
    )
    ticker: str | None = Field(
        default=None,
        description="Optional filter by company ticker (e.g. 'AAPL')",
    )
    filing_type: str | None = Field(
        default=None,
        description="Optional filter by filing type (e.g. '10-K', '10-Q')",
    )
    section_identifier: str | None = Field(
        default=None,
        description="Optional filter by section (e.g. 'ITEM_1A', 'ITEM_7')",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of ranked results to return",
    )
    similarity_threshold: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Minimum cosine similarity score required for inclusion",
    )


class SemanticSearchResult(BaseModel):
    """Ranked document chunk result with full filing and section provenance."""

    chunk_id: str = Field(..., description="Unique persistent chunk identifier")
    ticker: str = Field(..., description="Normalized company ticker symbol")
    company_name: str = Field(..., description="Official registered company title")
    cik: str = Field(..., description="10-digit zero-padded CIK number")
    filing_type: str = Field(..., description="Filing type (e.g. '10-K', '10-Q')")
    filing_date: str = Field(..., description="Filing submission date (YYYY-MM-DD)")
    report_date: str | None = Field(
        default=None,
        description="Filing period end date (YYYY-MM-DD)",
    )
    accession_number: str = Field(..., description="SEC EDGAR accession number")
    section_identifier: str = Field(
        ...,
        description="Canonical section identifier (e.g. 'ITEM_1A', 'ITEM_7')",
    )
    section_title: str = Field(..., description="Human-readable section title")
    chunk_text: str = Field(..., description="Original raw text of the chunk")
    similarity_score: float = Field(
        ...,
        description="Cosine similarity score between query and chunk vector [-1.0, 1.0]",
    )
    source_url: str = Field(..., description="Direct URL to filing on SEC EDGAR")


class IndexStatsResponse(BaseModel):
    """Operational statistics for the persistent vector store."""

    active_backend: str = Field(
        ...,
        description="Underlying vector engine ('faiss' or 'numpy')",
    )
    index_size: int = Field(
        ...,
        description="Number of vector embeddings currently loaded in the index",
    )
    embedding_dimension: int = Field(
        ...,
        description="Vector dimension size (e.g. 384)",
    )
    model_name: str = Field(
        ...,
        description="Pretrained sentence transformer model identifier",
    )
    index_location: str = Field(
        ...,
        description="Safe application-level index identifier (no absolute OS paths)",
    )
    last_updated_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of last index modification",
    )
    total_indexed_chunks: int = Field(
        default=0,
        description="Total distinct chunks mapped in database metadata",
    )


class ChunkEmbeddingRecord(BaseModel):
    """Database representation of an individual chunk embedding record."""

    model_config = ConfigDict(extra="ignore")

    embedding_id: str
    chunk_id: str
    document_id: str
    ticker: str
    accession_number: str
    section_identifier: str
    model_name: str
    model_version: str = "1.0"
    embedding_dimension: int
    embedding_input_hash: str
    chunk_text_hash: str
    vector_id: str
    index_status: Literal["indexed", "pending", "failed", "stale"] = "indexed"
    error_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
