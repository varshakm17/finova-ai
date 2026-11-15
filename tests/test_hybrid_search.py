"""Unit and integration tests for HybridSearchService and Reciprocal Rank Fusion.

Tests RRF mathematics, dual-source blending, candidate deduplication,
source score preservation, degraded-mode handling, and metadata filtering.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.data.document_storage import DocumentStorage
from backend.data.storage import Database
from backend.retrieval.bm25_search import BM25SearchService
from backend.retrieval.hybrid_search import HybridSearchService
from backend.retrieval.retrieval_models import SemanticSearchResult
from backend.retrieval.semantic_search import SemanticSearchService
from tests.test_bm25_search import seed_test_chunks


def test_rrf_score_calculation() -> None:
    """Verify reciprocal rank fusion formula: 1 / (k + rank)."""
    # k = 60
    # rank 1: 1 / (60 + 1) = 1 / 61 = 0.01639344...
    # rank 2: 1 / (60 + 2) = 1 / 62 = 0.01612903...
    score_r1 = HybridSearchService.calculate_rrf_score(rank=1, rrf_constant=60)
    assert pytest.approx(score_r1, rel=1e-5) == 1.0 / 61.0

    score_r2 = HybridSearchService.calculate_rrf_score(rank=2, rrf_constant=60)
    assert pytest.approx(score_r2, rel=1e-5) == 1.0 / 62.0

    # Custom k = 10
    score_k10 = HybridSearchService.calculate_rrf_score(rank=1, rrf_constant=10)
    assert pytest.approx(score_k10, rel=1e-5) == 1.0 / 11.0


def test_hybrid_search_fusion_logic(tmp_path: Path) -> None:
    """Verify blending of dense-only, sparse-only, and mutual candidate chunks."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)
    seed_test_chunks(storage)

    # Mock dense results: c1 (rank 1), c2 (rank 2)
    mock_dense_service = MagicMock(spec=SemanticSearchService)
    mock_dense_service.search.return_value = [
        SemanticSearchResult(
            chunk_id="chk_aapl_risk_01",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Item 1A. Risk Factors",
            chunk_text="Supply chain text",
            similarity_score=0.85,
            source_url="https://sec.gov",
        ),
        SemanticSearchResult(
            chunk_id="chk_aapl_mda_01",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_7",
            section_title="Item 7. MD&A",
            chunk_text="Cash flow text",
            similarity_score=0.72,
            source_url="https://sec.gov",
        ),
    ]

    # Mock sparse results: c1 (rank 2), c3 (rank 1)
    mock_bm25_service = MagicMock(spec=BM25SearchService)
    mock_s_c1 = MagicMock(
        chunk_id="chk_aapl_risk_01",
        ticker="AAPL",
        company_name="Apple Inc.",
        cik="0000320193",
        filing_type="10-K",
        filing_date="2023-11-03",
        report_date="2023-09-30",
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_1A",
        section_title="Item 1A. Risk Factors",
        chunk_text="Supply chain text",
        source_url="https://sec.gov",
        bm25_score=10.5,
    )
    mock_s_c3 = MagicMock(
        chunk_id="chk_msft_risk_01",
        ticker="MSFT",
        company_name="Microsoft Corporation",
        cik="0000789019",
        filing_type="10-K",
        filing_date="2023-07-28",
        report_date="2023-06-30",
        accession_number="0000789019-23-000050",
        section_identifier="ITEM_1A",
        section_title="Item 1A. Risk Factors",
        chunk_text="Cybersecurity text",
        source_url="https://sec.gov",
        bm25_score=14.2,
    )
    mock_bm25_service.search.return_value = [mock_s_c3, mock_s_c1]

    hybrid_service = HybridSearchService(
        semantic_search_service=mock_dense_service,
        bm25_search_service=mock_bm25_service,
        document_storage=storage,
    )

    resp = hybrid_service.search(query="supply chain risks", top_k=5, rrf_constant=60)
    assert resp.status == "success"
    assert resp.retrieval_mode == "hybrid"
    assert resp.total_results == 3

    # Chk_aapl_risk_01 appeared in BOTH:
    # Dense rank 1: 1/61 = 0.016393
    # Sparse rank 2: 1/62 = 0.016129
    # Total RRF: 0.016393 + 0.016129 = 0.032522
    top_result = resp.results[0]
    assert top_result.chunk_id == "chk_aapl_risk_01"
    assert "dense" in top_result.retrieval_sources
    assert "sparse" in top_result.retrieval_sources
    assert top_result.dense_rank == 1
    assert top_result.sparse_rank == 2
    assert top_result.dense_score == 0.85
    assert top_result.bm25_score == 10.5
    assert pytest.approx(top_result.rrf_score, rel=1e-4) == (1 / 61 + 1 / 62)

    # Chk_msft_risk_01 was sparse-only:
    # Sparse rank 1: 1/61 = 0.016393
    c3_res = next(r for r in resp.results if r.chunk_id == "chk_msft_risk_01")
    assert c3_res.retrieval_sources == ["sparse"]
    assert c3_res.dense_rank is None
    assert c3_res.dense_score is None
    assert c3_res.sparse_rank == 1
    assert c3_res.bm25_score == 14.2
    assert pytest.approx(c3_res.rrf_score, rel=1e-4) == (1 / 61)

    # Chk_aapl_mda_01 was dense-only:
    # Dense rank 2: 1/62 = 0.016129
    c2_res = next(r for r in resp.results if r.chunk_id == "chk_aapl_mda_01")
    assert c2_res.retrieval_sources == ["dense"]
    assert c2_res.dense_rank == 2
    assert c2_res.sparse_rank is None
    assert pytest.approx(c2_res.rrf_score, rel=1e-4) == (1 / 62)


def test_hybrid_search_degraded_mode_dense_failure(tmp_path: Path) -> None:
    """Verify degraded mode when dense search raises an exception."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)

    mock_dense_service = MagicMock(spec=SemanticSearchService)
    mock_dense_service.search.side_effect = RuntimeError("FAISS index corrupted")

    mock_bm25_service = MagicMock(spec=BM25SearchService)
    mock_bm25_service.search.return_value = [
        MagicMock(
            chunk_id="chk_sparse_1",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk",
            chunk_text="Some text",
            source_url="https://sec.gov",
            bm25_score=8.5,
        )
    ]

    service = HybridSearchService(
        semantic_search_service=mock_dense_service,
        bm25_search_service=mock_bm25_service,
        document_storage=storage,
    )

    resp = service.search(query="supply chain")
    assert resp.status == "degraded"
    assert resp.retrieval_mode == "hybrid_degraded_sparse_only"
    assert len(resp.warnings) == 1
    assert "FAISS index corrupted" in resp.warnings[0]
    assert resp.total_results == 1
    assert resp.results[0].retrieval_sources == ["sparse"]


def test_hybrid_search_degraded_mode_sparse_failure(tmp_path: Path) -> None:
    """Verify degraded mode when sparse search raises an exception."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)

    mock_dense_service = MagicMock(spec=SemanticSearchService)
    mock_dense_service.search.return_value = [
        SemanticSearchResult(
            chunk_id="chk_dense_1",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Risk",
            chunk_text="Some text",
            similarity_score=0.9,
            source_url="https://sec.gov",
        )
    ]

    mock_bm25_service = MagicMock(spec=BM25SearchService)
    mock_bm25_service.search.side_effect = OSError("BM25 corpus file missing")

    service = HybridSearchService(
        semantic_search_service=mock_dense_service,
        bm25_search_service=mock_bm25_service,
        document_storage=storage,
    )

    resp = service.search(query="supply chain")
    assert resp.status == "degraded"
    assert resp.retrieval_mode == "hybrid_degraded_dense_only"
    assert len(resp.warnings) == 1
    assert "BM25 corpus file missing" in resp.warnings[0]
    assert resp.total_results == 1
    assert resp.results[0].retrieval_sources == ["dense"]


def test_hybrid_search_both_fail(tmp_path: Path) -> None:
    """Verify error status when both retrieval engines fail."""
    db = Database(db_path=str(tmp_path / "test.db"))
    storage = DocumentStorage(db=db)

    mock_dense = MagicMock(spec=SemanticSearchService)
    mock_dense.search.side_effect = RuntimeError("Dense failure")

    mock_bm25 = MagicMock(spec=BM25SearchService)
    mock_bm25.search.side_effect = RuntimeError("Sparse failure")

    service = HybridSearchService(
        semantic_search_service=mock_dense,
        bm25_search_service=mock_bm25,
        document_storage=storage,
    )

    resp = service.search(query="supply chain")
    assert resp.status == "error"
    assert resp.retrieval_mode == "hybrid_failed"
    assert resp.total_results == 0
    assert len(resp.warnings) == 2


def test_hybrid_search_empty_query() -> None:
    """Verify empty query raises ValueError."""
    service = HybridSearchService()
    with pytest.raises(ValueError, match="cannot be empty"):
        service.search(query="   ")
