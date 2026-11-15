"""Pydantic schemas and data models for semantic embeddings and vector retrieval.

Defines request and response contracts for document chunk indexing,
indexing status diagnostics, semantic similarity search, and vector store statistics.
"""

from datetime import UTC, datetime
from typing import Any, Literal

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


# ==============================================================================
# BM25 Sparse Retrieval Models (Session 06)
# ==============================================================================


class BM25IndexingRequest(BaseModel):
    """Request payload for triggering BM25 index generation or update."""

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
        description="If True, re-tokenizes and updates chunks even if content hash matches",
    )


class BM25IndexingSummary(BaseModel):
    """Summary of batch BM25 indexing run."""

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
        description="Chunks skipped because valid up-to-date BM25 tokens exist",
    )
    newly_indexed: int = Field(
        ...,
        description="Newly tokenized chunks added to BM25 index and database",
    )
    updated_indexed: int = Field(
        ...,
        description="Chunks re-tokenized due to text change or force_reindex",
    )
    removed: int = Field(
        default=0,
        description="Chunks removed from BM25 index that no longer exist in storage",
    )
    failed: int = Field(
        ...,
        description="Number of chunks that failed tokenization or persistence",
    )
    tokenizer_version: str = Field(
        ...,
        description="Active BM25 financial tokenizer version",
    )
    duration_seconds: float = Field(
        ...,
        description="Total elapsed wall-clock processing time in seconds",
    )
    message: str | None = Field(
        default=None,
        description="Descriptive status message or warning details",
    )


class BM25IndexStatusResponse(BaseModel):
    """Diagnostics detailing BM25 indexing coverage for a company."""

    ticker: str = Field(..., description="Target company ticker symbol")
    total_available_chunks: int = Field(
        ...,
        description="Total document chunks stored in SQLite for this company",
    )
    indexed_chunks: int = Field(
        ...,
        description="Total chunks successfully indexed in the BM25 index",
    )
    pending_chunks: int = Field(
        ...,
        description="Chunks awaiting BM25 indexing",
    )
    failed_chunks: int = Field(
        ...,
        description="Chunks whose last BM25 attempt recorded an error",
    )
    tokenizer_version: str = Field(
        ...,
        description="Active tokenizer version identifier",
    )
    total_tokens: int = Field(
        default=0,
        description="Total tokens indexed across company chunks",
    )
    avg_doc_len: float = Field(
        default=0.0,
        description="Average token length of indexed chunks for this company",
    )
    last_indexed_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of last index update",
    )


class BM25SearchRequest(BaseModel):
    """Query parameters for BM25 sparse lexical search over filing chunks."""

    query: str = Field(
        ...,
        min_length=1,
        description="Lexical keyword query, exact phrase, acronym, or financial metric",
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


class BM25SearchResult(BaseModel):
    """Ranked document chunk result from BM25 lexical search."""

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
    bm25_score: float = Field(
        ...,
        description="Raw BM25 Okapi lexical score (higher indicates greater relevance)",
    )
    source_url: str = Field(..., description="Direct URL to filing on SEC EDGAR")
    matched_terms: list[str] = Field(
        default_factory=list,
        description="Query terms found in this document chunk",
    )


class BM25IndexStatsResponse(BaseModel):
    """Operational statistics for the persistent BM25 sparse index."""

    total_chunks: int = Field(
        ...,
        description="Number of document chunks currently in the BM25 index",
    )
    tokenizer_version: str = Field(
        ...,
        description="Active financial tokenizer version",
    )
    vocab_size: int = Field(
        ...,
        description="Number of distinct terms in the BM25 vocabulary",
    )
    avg_doc_len: float = Field(
        ...,
        description="Average token length across all indexed chunks",
    )
    index_location: str = Field(
        ...,
        description="Safe application-level index identifier (no absolute OS paths)",
    )
    last_updated_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp of last index modification",
    )
    indexed_tickers: list[str] = Field(
        default_factory=list,
        description="List of tickers represented in the BM25 index",
    )


# ==============================================================================
# Hybrid Search & Reciprocal Rank Fusion Models (Session 06)
# ==============================================================================


class HybridSearchRequest(BaseModel):
    """Query parameters for hybrid dense-sparse retrieval combining vector similarity and BM25."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language question or financial search query",
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
        description="Maximum number of fused results to return",
    )
    rrf_constant: int = Field(
        default=60,
        ge=1,
        le=200,
        description="Reciprocal Rank Fusion smoothing parameter k (standard: 60)",
    )
    dense_limit: int = Field(
        default=50,
        ge=5,
        le=200,
        description="Candidate pool size retrieved from dense semantic search",
    )
    sparse_limit: int = Field(
        default=50,
        ge=5,
        le=200,
        description="Candidate pool size retrieved from BM25 sparse search",
    )


class HybridSearchResult(BaseModel):
    """Ranked document chunk result combining dense and sparse retrieval with provenance."""

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
    source_url: str = Field(..., description="Direct URL to filing on SEC EDGAR")
    dense_rank: int | None = Field(
        default=None,
        description="1-based rank in dense semantic search results, if present",
    )
    dense_score: float | None = Field(
        default=None,
        description="Cosine similarity score from dense search, if present",
    )
    sparse_rank: int | None = Field(
        default=None,
        description="1-based rank in BM25 sparse search results, if present",
    )
    bm25_score: float | None = Field(
        default=None,
        description="BM25 lexical score from sparse search, if present",
    )
    rrf_score: float = Field(
        ...,
        description="Reciprocal Rank Fusion score: sum(1 / (k + rank_r))",
    )
    retrieval_sources: list[str] = Field(
        ...,
        description="Retriever components that discovered this chunk (e.g. ['dense', 'sparse'])",
    )


class HybridSearchResponse(BaseModel):
    """Response payload for hybrid search containing ranked results and operational diagnostics."""

    query: str = Field(..., description="Submitted query string")
    retrieval_mode: str = Field(
        default="hybrid",
        description="Execution mode: 'hybrid', 'dense_only', 'sparse_only', or degraded variants",
    )
    status: Literal["success", "degraded", "error"] = Field(
        default="success",
        description="Execution status indicating normal or degraded hybrid retrieval",
    )
    total_results: int = Field(
        ...,
        description="Number of final ranked results returned",
    )
    results: list[HybridSearchResult] = Field(
        default_factory=list,
        description="Ranked list of fused search results in descending RRF order",
    )
    diagnostics: dict[str, Any] | None = Field(
        default=None,
        description="Operational diagnostics including candidate counts and execution timings",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Diagnostic warnings or degraded-mode notifications",
    )


# ==============================================================================
# Cross-Encoder Reranking Models (Session 07)
# ==============================================================================


class RerankedSearchResult(BaseModel):
    """Document chunk result after cross-encoder reranking, preserving provenance."""

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
    source_url: str = Field(..., description="Direct URL to filing on SEC EDGAR")
    original_rank: int = Field(
        ...,
        description="Original 1-based rank from initial retriever (e.g. hybrid RRF rank)",
    )
    rerank_rank: int = Field(
        ...,
        description="Final 1-based rank after cross-encoder reranking",
    )
    rerank_score: float = Field(
        ...,
        description="Relevance score assigned by the cross-encoder model",
    )
    original_dense_rank: int | None = Field(
        default=None,
        description="1-based rank in dense search, if retrieved by dense",
    )
    original_dense_score: float | None = Field(
        default=None,
        description="Dense cosine similarity score, if available",
    )
    original_sparse_rank: int | None = Field(
        default=None,
        description="1-based rank in sparse search, if retrieved by sparse",
    )
    original_bm25_score: float | None = Field(
        default=None,
        description="BM25 lexical score, if available",
    )
    original_rrf_score: float | None = Field(
        default=None,
        description="RRF score prior to reranking",
    )
    retrieval_sources: list[str] = Field(
        default_factory=list,
        description="Retriever components that discovered this chunk",
    )


class RerankerStatusResponse(BaseModel):
    """Operational status and configuration of the cross-encoder reranker."""

    enabled: bool = Field(
        ..., description="Whether reranking is enabled in configuration"
    )
    model_name: str = Field(..., description="Name or path of the cross-encoder model")
    device: str = Field(..., description="Compute device ('cpu' or 'cuda')")
    batch_size: int = Field(
        ..., description="Candidate batch size for reranker scoring"
    )
    candidate_count: int = Field(
        ..., description="Number of candidate chunks sent for reranking"
    )
    initialized: bool = Field(
        ..., description="Whether model weights are loaded in memory"
    )
    is_available: bool = Field(
        ..., description="Whether reranker is ready to process queries"
    )
    benchmarked: bool = Field(
        default=False,
        description="Whether CPU inference benchmark has run in this session",
    )
    last_benchmark_latency_ms: float | None = Field(
        default=None,
        description="Measured inference latency for candidate batch (milliseconds)",
    )
    message: str | None = Field(
        default=None,
        description="Status message or warning if degraded/unavailable",
    )


# ==============================================================================
# Retrieval Evaluation & Comparison Models (Session 07)
# ==============================================================================


class EvaluationQuery(BaseModel):
    """Schema for an individual evaluation query with ground-truth relevant chunks."""

    query_id: str = Field(..., description="Unique evaluation query identifier")
    query: str = Field(..., description="Natural language search query")
    ticker: str | None = Field(default=None, description="Optional ticker filter")
    filing_type: str | None = Field(
        default=None, description="Optional filing type filter"
    )
    section_identifier: str | None = Field(
        default=None, description="Optional section filter"
    )
    relevant_chunk_ids: list[str] = Field(
        default_factory=list,
        description="List of known relevant chunk IDs",
    )
    relevance_grades: dict[str, int] = Field(
        default_factory=dict,
        description="Optional mapping from chunk_id to integer grade (0=unrelated, 1=partial, 2=exact)",
    )
    dataset_type: str = Field(
        default="synthetic",
        description="'synthetic' fixture or 'curated' human financial analyst judgment",
    )
    notes: str | None = Field(
        default=None, description="Annotation rationale or context"
    )


class RetrievalEvaluationRequest(BaseModel):
    """Request payload to execute retrieval evaluation on a benchmark dataset."""

    dataset_path: str | None = Field(
        default=None,
        description="Path to evaluation JSON dataset (defaults to configured setting)",
    )
    retrieval_method: Literal["dense", "sparse", "hybrid", "hybrid_reranked"] = Field(
        default="hybrid",
        description="Retrieval method to evaluate",
    )
    top_k: int = Field(
        default=5, ge=1, le=50, description="Cutoff rank for metrics evaluation"
    )
    rerank: bool = Field(
        default=False, description="Whether to apply cross-encoder reranking"
    )
    ticker_filter: str | None = Field(
        default=None,
        description="Optional ticker symbol to restrict evaluation queries to",
    )


class PerQueryMetric(BaseModel):
    """Deterministic evaluation metrics for a single query."""

    query_id: str = Field(..., description="Evaluation query identifier")
    query: str = Field(..., description="Query text evaluated")
    expected_relevant_count: int = Field(
        ..., description="Count of known relevant chunks"
    )
    retrieved_count: int = Field(
        ..., description="Number of results returned by retriever"
    )
    relevant_retrieved_count: int = Field(
        ..., description="Relevant results found in top-k"
    )
    precision_at_k: float = Field(..., description="Precision at cutoff k")
    recall_at_k: float = Field(..., description="Recall at cutoff k")
    reciprocal_rank: float = Field(
        ..., description="Reciprocal rank of first relevant chunk (1/rank)"
    )
    average_precision: float = Field(
        ..., description="Average precision for this query"
    )
    ndcg_at_k: float = Field(
        ..., description="Normalized Discounted Cumulative Gain at cutoff k"
    )
    retrieved_chunk_ids: list[str] = Field(
        default_factory=list, description="IDs of chunks retrieved"
    )
    latency_ms: float = Field(
        default=0.0, description="Query execution time in milliseconds"
    )


class RetrievalMetricResult(BaseModel):
    """Summary of deterministic evaluation metrics across a query dataset."""

    precision_at_k: float = Field(..., description="Macro-averaged Precision@K")
    recall_at_k: float = Field(..., description="Macro-averaged Recall@K")
    recall_at_5: float = Field(..., description="Macro-averaged Recall@5")
    recall_at_10: float = Field(..., description="Macro-averaged Recall@10")
    recall_at_20: float = Field(..., description="Macro-averaged Recall@20")
    mrr: float = Field(..., description="Mean Reciprocal Rank (MRR)")
    map_score: float = Field(..., description="Mean Average Precision (MAP)")
    ndcg_at_k: float = Field(..., description="Macro-averaged NDCG@K")
    coverage: float = Field(
        ..., description="Fraction of queries that returned >= 1 result"
    )
    k: int = Field(..., description="Cutoff rank k used for evaluation")
    evaluated_queries_count: int = Field(
        ..., description="Total queries successfully evaluated"
    )
    skipped_queries_count: int = Field(
        default=0,
        description="Queries skipped (e.g. zero ground truth labels)",
    )
    macro_precision: float = Field(..., description="Macro-averaged Precision")
    micro_precision: float = Field(
        ..., description="Micro-averaged Precision across all results"
    )
    macro_recall: float = Field(..., description="Macro-averaged Recall")
    micro_recall: float = Field(
        ..., description="Micro-averaged Recall across all results"
    )


class RetrievalEvaluationReport(BaseModel):
    """Complete evaluation report for a retrieval method over a dataset."""

    report_id: str = Field(..., description="Unique generated report identifier")
    evaluation_method: str = Field(..., description="Evaluated method name")
    dataset_identifier: str = Field(
        ..., description="Identifier or path of evaluation dataset"
    )
    dataset_type: str = Field(
        default="synthetic",
        description="'synthetic' fixture or 'curated' human financial analyst judgment",
    )
    metrics: RetrievalMetricResult = Field(..., description="Aggregated metric summary")
    per_query_results: list[PerQueryMetric] = Field(
        default_factory=list,
        description="Individual per-query metric records",
    )
    execution_time_seconds: float = Field(
        ..., description="Total evaluation run duration"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 creation timestamp",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Evaluation warnings or notices",
    )


class RetrievalComparisonRequest(BaseModel):
    """Request payload to execute fair comparative evaluation across all retrieval methods."""

    dataset_path: str | None = Field(
        default=None,
        description="Optional custom path to evaluation dataset JSON",
    )
    top_k: int = Field(
        default=5, ge=1, le=50, description="Common top-k cutoff for all methods"
    )
    include_reranking: bool = Field(
        default=True,
        description="Whether to include reranked hybrid in the comparative benchmark",
    )
    ticker_filter: str | None = Field(
        default=None,
        description="Optional ticker symbol to restrict comparison to",
    )


class MethodComparisonSummary(BaseModel):
    """Metric summary for an individual retrieval method within a comparative benchmark."""

    method: str = Field(
        ..., description="Method name: dense, sparse, hybrid, or hybrid_reranked"
    )
    precision_at_k: float = Field(..., description="Precision at cutoff k")
    recall_at_k: float = Field(..., description="Recall at cutoff k")
    mrr: float = Field(..., description="Mean Reciprocal Rank")
    map_score: float = Field(..., description="Mean Average Precision")
    ndcg_at_k: float = Field(..., description="NDCG at cutoff k")
    coverage: float = Field(..., description="Result coverage ratio")
    avg_latency_ms: float = Field(
        ..., description="Average query latency in milliseconds"
    )


class RetrievalComparisonResponse(BaseModel):
    """Fair comparative evaluation report across dense, sparse, hybrid, and reranked retrieval."""

    dataset_identifier: str = Field(..., description="Evaluation dataset identifier")
    total_queries: int = Field(..., description="Total queries evaluated")
    top_k: int = Field(..., description="Evaluation rank cutoff k")
    methods_evaluated: list[str] = Field(
        ..., description="List of retrieval methods benchmarked"
    )
    method_summaries: dict[str, MethodComparisonSummary] = Field(
        ...,
        description="Per-method aggregated metrics",
    )
    hybrid_delta_vs_dense: dict[str, float] = Field(
        ...,
        description="Relative metric percentage changes of hybrid over dense baseline",
    )
    hybrid_delta_vs_sparse: dict[str, float] = Field(
        ...,
        description="Relative metric percentage changes of hybrid over sparse baseline",
    )
    reranked_delta_vs_hybrid: dict[str, float] | None = Field(
        default=None,
        description="Relative metric percentage changes of reranked hybrid over standard hybrid",
    )
    per_query_comparisons: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-query method ranking breakdowns and overlap",
    )
    duration_seconds: float = Field(
        ..., description="Total benchmark run duration in seconds"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 creation timestamp",
    )


# ==============================================================================
# Evidence Quality Validation Models (Session 07)
# ==============================================================================


class EvidenceChunkValidation(BaseModel):
    """Deterministic validation results for an individual retrieved evidence chunk."""

    chunk_id: str = Field(..., description="Validated chunk identifier")
    status: Literal[
        "valid",
        "incomplete_provenance",
        "source_mismatch",
        "possible_duplicate",
        "temporal_mismatch",
        "requires_review",
    ] = Field(..., description="Categorical validation status")
    warnings: list[str] = Field(
        default_factory=list, description="Descriptive validation warnings"
    )
    provenance_complete: bool = Field(
        ..., description="Whether all required statutory fields exist"
    )
    source_domain_valid: bool = Field(
        ..., description="Whether source_url is on official SEC domain"
    )
    document_matched: bool | None = Field(
        default=None,
        description="Whether chunk matches a persistent filing document record in storage",
    )
    is_duplicate: bool = Field(
        default=False,
        description="Whether this chunk is an exact or near duplicate of another retrieved chunk",
    )
    duplicate_of_chunk_id: str | None = Field(
        default=None,
        description="ID of the earlier chunk this chunk duplicates",
    )
    reporting_period: str | None = Field(
        default=None,
        description="Extracted financial period (e.g. '2023-09-30')",
    )
    filing_date: str | None = Field(
        default=None,
        description="Filing submission date (e.g. '2023-11-03')",
    )
    source_url: str = Field(..., description="Direct SEC EDGAR source link")


class EvidenceValidationRequest(BaseModel):
    """Request payload to validate retrieved evidence chunks."""

    chunk_ids: list[str] = Field(
        default_factory=list,
        description="List of specific chunk IDs to validate against storage",
    )
    query: str | None = Field(
        default=None,
        description="Optional search query to retrieve and validate fresh results for",
    )
    retrieval_method: str = Field(
        default="hybrid",
        description="Retrieval method to execute if query is provided ('dense', 'sparse', 'hybrid')",
    )
    top_k: int = Field(
        default=5, ge=1, le=50, description="Top-k chunks to retrieve and validate"
    )


class EvidenceValidationResult(BaseModel):
    """Summary of deterministic evidence quality inspection across retrieved chunks."""

    total_chunks_inspected: int = Field(
        ..., description="Number of evidence chunks analyzed"
    )
    valid_count: int = Field(
        ..., description="Count of chunks meeting all provenance standards"
    )
    warning_count: int = Field(
        ..., description="Count of chunks raising warnings or reviews"
    )
    overall_status: Literal["valid", "requires_review", "invalid"] = Field(
        ...,
        description="Overall quality classification for the retrieved evidence set",
    )
    chunk_validations: list[EvidenceChunkValidation] = Field(
        default_factory=list,
        description="Per-chunk validation records",
    )
    distinct_reporting_periods: list[str] = Field(
        default_factory=list,
        description="Unique financial reporting periods detected among evidence chunks",
    )
    duplicate_clusters: list[list[str]] = Field(
        default_factory=list,
        description="Clusters of duplicate or highly overlapping chunk IDs",
    )
    summary_notes: list[str] = Field(
        default_factory=list,
        description="High-level audit findings and recommendations",
    )


class EvidenceReport(BaseModel):
    """LLM-ready structured evidence brief consolidating retrieved chunks and provenance."""

    report_id: str = Field(..., description="Unique evidence report identifier")
    query: str = Field(..., description="Target financial research query")
    retrieval_method: str = Field(..., description="Retrieval method utilized")
    reranker_applied: bool = Field(
        default=False, description="Whether reranking was executed"
    )
    reranker_model: str | None = Field(
        default=None, description="Active cross-encoder model"
    )
    ranked_candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ranked candidate chunks with provenance, scores, and validation status",
    )
    validation_summary: EvidenceValidationResult = Field(
        ...,
        description="Evidence quality validation summary",
    )
    distinct_periods: list[str] = Field(
        default_factory=list,
        description="Unique financial periods represented in evidence",
    )
    sec_source_links: list[str] = Field(
        default_factory=list,
        description="Verified SEC EDGAR direct links for citation",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp",
    )
