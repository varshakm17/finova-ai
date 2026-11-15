"""Unit tests for RetrievalDiagnostics.

Tests diagnostic metrics, overlap calculation, Jaccard similarity,
rank shift analysis, and synthetic query benchmark runner.
"""

from unittest.mock import MagicMock

from backend.evaluation.retrieval_diagnostics import (
    DiagnosticComparison,
    RetrievalDiagnostics,
)
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.retrieval_models import HybridSearchResponse, HybridSearchResult


def test_retrieval_diagnostics_analysis() -> None:
    """Verify diagnostic metrics calculation for overlap, Jaccard, and rank shifts."""
    mock_hybrid = MagicMock(spec=HybridSearchService)

    sample_results = [
        HybridSearchResult(
            chunk_id="chk_1",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="accn1",
            section_identifier="ITEM_1A",
            section_title="Risk",
            chunk_text="Supply chain text",
            source_url="https://sec.gov",
            dense_rank=1,
            dense_score=0.88,
            sparse_rank=2,
            bm25_score=11.2,
            rrf_score=0.0325,
            retrieval_sources=["dense", "sparse"],
        ),
        HybridSearchResult(
            chunk_id="chk_2",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="accn1",
            section_identifier="ITEM_7",
            section_title="MD&A",
            chunk_text="Cash flow text",
            source_url="https://sec.gov",
            dense_rank=2,
            dense_score=0.75,
            sparse_rank=None,
            bm25_score=None,
            rrf_score=0.0161,
            retrieval_sources=["dense"],
        ),
    ]

    mock_hybrid.search.return_value = HybridSearchResponse(
        query="supply chain risks",
        retrieval_mode="hybrid",
        status="success",
        total_results=2,
        results=sample_results,
        diagnostics={
            "dense_candidates_count": 2,
            "sparse_candidates_count": 1,
            "total_unique_candidates": 2,
            "overlap_candidates_count": 1,
            "total_duration_seconds": 0.045,
        },
    )

    diagnostics = RetrievalDiagnostics(hybrid_service=mock_hybrid)
    diag = diagnostics.analyze_query(query="supply chain risks", top_k=5)

    assert isinstance(diag, DiagnosticComparison)
    assert diag.dense_candidates_count == 2
    assert diag.sparse_candidates_count == 1
    assert diag.overlap_count == 1
    assert diag.dense_exclusive_count == 1
    assert diag.sparse_exclusive_count == 0
    # Jaccard = overlap / (dense + sparse - overlap) = 1 / (2 + 1 - 1) = 1 / 2 = 0.5
    assert diag.jaccard_overlap_ratio == 0.5
    assert len(diag.rank_shifts) == 2
    assert diag.rank_shifts[0]["sources"] == ["dense", "sparse"]
    assert diag.rank_shifts[1]["sources"] == ["dense"]

    d_dict = diag.to_dict()
    assert d_dict["overlap_count"] == 1
    assert d_dict["jaccard_overlap_ratio"] == 0.5


def test_synthetic_benchmark_runner() -> None:
    """Verify synthetic benchmark executes across benchmark suite queries."""
    mock_hybrid = MagicMock(spec=HybridSearchService)
    mock_hybrid.search.return_value = HybridSearchResponse(
        query="test query",
        retrieval_mode="hybrid",
        status="success",
        total_results=1,
        results=[
            HybridSearchResult(
                chunk_id="chk_test",
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="accn",
                section_identifier="ITEM_1A",
                section_title="Risk",
                chunk_text="Test",
                source_url="https://sec.gov",
                rrf_score=0.016,
                retrieval_sources=["dense"],
            )
        ],
        diagnostics={
            "dense_candidates_count": 1,
            "sparse_candidates_count": 1,
            "total_unique_candidates": 1,
            "overlap_candidates_count": 1,
        },
    )

    diagnostics = RetrievalDiagnostics(hybrid_service=mock_hybrid)
    bench_results = diagnostics.run_synthetic_benchmark(ticker="AAPL", top_k=5)

    assert len(bench_results) == 4
    for b in bench_results:
        assert "query_id" in b
        assert "matching_expected_section_count" in b
        assert "jaccard_overlap" in b
