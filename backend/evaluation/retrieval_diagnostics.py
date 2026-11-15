"""Retrieval Diagnostics and Evaluation Utilities for Finova AI.

Provides metrics to measure overlap between dense and sparse retrieval,
fusion rank shifts, execution timings, and synthetic offline benchmark suites.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.retrieval_models import HybridSearchResult


@dataclass
class DiagnosticComparison:
    """Detailed diagnostics comparing dense, sparse, and hybrid search outcomes."""

    query: str
    total_duration_seconds: float
    dense_candidates_count: int
    sparse_candidates_count: int
    unique_candidates_count: int
    overlap_count: int
    jaccard_overlap_ratio: float
    dense_exclusive_count: int
    sparse_exclusive_count: int
    top_k: int
    results: list[HybridSearchResult] = field(default_factory=list)
    rank_shifts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert diagnostic comparison to dictionary."""
        return {
            "query": self.query,
            "total_duration_seconds": self.total_duration_seconds,
            "dense_candidates_count": self.dense_candidates_count,
            "sparse_candidates_count": self.sparse_candidates_count,
            "unique_candidates_count": self.unique_candidates_count,
            "overlap_count": self.overlap_count,
            "jaccard_overlap_ratio": self.jaccard_overlap_ratio,
            "dense_exclusive_count": self.dense_exclusive_count,
            "sparse_exclusive_count": self.sparse_exclusive_count,
            "top_k": self.top_k,
            "rank_shifts": self.rank_shifts,
        }


# Synthetic benchmark query suite for deterministic offline testing.
# NOTE: This synthetic dataset verifies retrieval mechanics and rank fusion behavior.
# It is not a substitute for human-annotated financial expert relevance benchmarks.
SYNTHETIC_BENCHMARK_QUERIES = [
    {
        "query_id": "SYN-001",
        "query": "What are the company's primary supply chain and manufacturing risks?",
        "ticker": "AAPL",
        "expected_section": "ITEM_1A",
        "keywords": ["supply", "chain", "manufacturing", "risk"],
    },
    {
        "query_id": "SYN-002",
        "query": "What factors drove operating revenue growth year-over-year?",
        "ticker": "AAPL",
        "expected_section": "ITEM_7",
        "keywords": ["revenue", "growth", "year-over-year", "operating"],
    },
    {
        "query_id": "SYN-003",
        "query": "What disclosures are made regarding liquidity constraints and long-term debt?",
        "ticker": "AAPL",
        "expected_section": "ITEM_7",
        "keywords": ["liquidity", "debt", "cash-flow"],
    },
    {
        "query_id": "SYN-004",
        "query": "Quantitative and qualitative disclosures about interest rate and currency market risks",
        "ticker": "AAPL",
        "expected_section": "ITEM_7A",
        "keywords": ["interest", "rate", "currency", "market"],
    },
]


class RetrievalDiagnostics:
    """Analyzer providing diagnostic comparisons across retrieval modalities."""

    def __init__(self, hybrid_service: HybridSearchService) -> None:
        self.hybrid_service = hybrid_service

    def analyze_query(
        self,
        query: str,
        ticker: str | None = None,
        filing_type: str | None = None,
        section_identifier: str | None = None,
        top_k: int = 10,
        rrf_constant: int = 60,
    ) -> DiagnosticComparison:
        """Run hybrid search and produce detailed diagnostics comparing modalities.

        Args:
            query: Query to evaluate.
            ticker: Optional ticker filter.
            filing_type: Optional filing type filter.
            section_identifier: Optional section filter.
            top_k: Top-k result limit.
            rrf_constant: Smoothing parameter for RRF.

        Returns:
            DiagnosticComparison: Diagnostic metrics and rank analysis.
        """
        start = time.perf_counter()
        resp = self.hybrid_service.search(
            query=query,
            ticker=ticker,
            filing_type=filing_type,
            section_identifier=section_identifier,
            top_k=top_k,
            rrf_constant=rrf_constant,
        )
        total_dur = time.perf_counter() - start

        diag = resp.diagnostics or {}
        dense_c = diag.get("dense_candidates_count", 0)
        sparse_c = diag.get("sparse_candidates_count", 0)
        overlap = diag.get("overlap_candidates_count", 0)
        unique_c = diag.get("total_unique_candidates", 0)

        union_size = dense_c + sparse_c - overlap
        jaccard = (overlap / max(1, union_size)) if union_size > 0 else 0.0

        dense_exclusive = dense_c - overlap
        sparse_exclusive = sparse_c - overlap

        rank_shifts: list[dict[str, Any]] = []
        for hybrid_rank, res in enumerate(resp.results, start=1):
            rank_shifts.append(
                {
                    "hybrid_rank": hybrid_rank,
                    "chunk_id": res.chunk_id,
                    "dense_rank": res.dense_rank,
                    "sparse_rank": res.sparse_rank,
                    "dense_score": res.dense_score,
                    "bm25_score": res.bm25_score,
                    "rrf_score": res.rrf_score,
                    "sources": res.retrieval_sources,
                }
            )

        return DiagnosticComparison(
            query=query,
            total_duration_seconds=round(total_dur, 4),
            dense_candidates_count=dense_c,
            sparse_candidates_count=sparse_c,
            unique_candidates_count=unique_c,
            overlap_count=overlap,
            jaccard_overlap_ratio=round(jaccard, 4),
            dense_exclusive_count=dense_exclusive,
            sparse_exclusive_count=sparse_exclusive,
            top_k=top_k,
            results=resp.results,
            rank_shifts=rank_shifts,
        )

    def run_synthetic_benchmark(
        self,
        ticker: str = "AAPL",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Execute the synthetic query benchmark suite against the current index.

        Args:
            ticker: Ticker symbol to query.
            top_k: Top-k per benchmark query.

        Returns:
            list[dict[str, Any]]: Per-query benchmark evaluation metrics.
        """
        results: list[dict[str, Any]] = []
        for item in SYNTHETIC_BENCHMARK_QUERIES:
            diag = self.analyze_query(
                query=item["query"],
                ticker=ticker,
                top_k=top_k,
            )
            # Check how many results matched the expected section
            expected_sec = item["expected_section"]
            matching_sec_count = sum(
                1 for r in diag.results if r.section_identifier == expected_sec
            )

            results.append(
                {
                    "query_id": item["query_id"],
                    "query": item["query"],
                    "total_returned": len(diag.results),
                    "matching_expected_section_count": matching_sec_count,
                    "overlap_count": diag.overlap_count,
                    "jaccard_overlap": diag.jaccard_overlap_ratio,
                    "duration_seconds": diag.total_duration_seconds,
                }
            )

        return results
