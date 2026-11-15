"""Integration tests for BM25 Sparse & Hybrid Search REST API endpoints.

Tests request validation, 404 on unknown tickers, 400 on empty queries,
indexing summaries, sparse search, and hybrid RRF responses.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.retrieval.retrieval_models import (
    BM25IndexingSummary,
    BM25IndexStatsResponse,
    BM25IndexStatusResponse,
    BM25SearchResult,
    HybridSearchResponse,
    HybridSearchResult,
)


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_api_bm25_index_company_success(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/bm25/index."""
    mock_summary = BM25IndexingSummary(
        ticker="AAPL",
        total_discovered=10,
        already_indexed=0,
        newly_indexed=10,
        updated_indexed=0,
        removed=0,
        failed=0,
        tokenizer_version="1.0.0",
        duration_seconds=0.15,
        message="Indexed 10 chunks",
    )

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL", "name": "Apple Inc."},
        ),
        patch(
            "backend.api.routes._bm25_indexing_service.index_company_chunks",
            return_value=mock_summary,
        ),
    ):
        resp = client.post(
            "/api/v1/companies/AAPL/bm25/index",
            json={"force_reindex": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["newly_indexed"] == 10
        assert data["total_discovered"] == 10


def test_api_bm25_index_company_not_found(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/bm25/index returns 404 for unknown ticker."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker", return_value=None
    ):
        resp = client.post("/api/v1/companies/NONEXISTENT/bm25/index")
        assert resp.status_code == 404
        error_msg = resp.json().get("message") or resp.json().get("detail", "")
        assert "not found" in error_msg.lower()


def test_api_bm25_status_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/bm25/status."""
    mock_status = BM25IndexStatusResponse(
        ticker="AAPL",
        total_available_chunks=25,
        indexed_chunks=25,
        pending_chunks=0,
        failed_chunks=0,
        tokenizer_version="1.0.0",
        total_tokens=15000,
        avg_doc_len=600.0,
        last_indexed_at="2026-11-15T20:00:00Z",
    )

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._bm25_indexing_service.get_indexing_status",
            return_value=mock_status,
        ),
    ):
        resp = client.get("/api/v1/companies/AAPL/bm25/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["indexed_chunks"] == 25
        assert data["total_tokens"] == 15000


def test_api_bm25_search_sparse_success(client: TestClient) -> None:
    """Verify POST /api/v1/search/sparse returns ranked BM25 results."""
    mock_results = [
        BM25SearchResult(
            chunk_id="chk_01",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Item 1A. Risk Factors",
            chunk_text="Supply chain disruptions in Asia.",
            bm25_score=12.45,
            source_url="https://sec.gov",
            matched_terms=["supply", "chain"],
        )
    ]

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._bm25_search_service.search", return_value=mock_results
        ),
    ):
        resp = client.post(
            "/api/v1/search/sparse",
            json={
                "query": "supply chain disruptions",
                "ticker": "AAPL",
                "top_k": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["chunk_id"] == "chk_01"
        assert data[0]["bm25_score"] == 12.45
        assert "supply" in data[0]["matched_terms"]


def test_api_bm25_search_sparse_empty_query(client: TestClient) -> None:
    """Verify POST /api/v1/search/sparse returns 400 for empty query."""
    resp = client.post("/api/v1/search/sparse", json={"query": "   "})
    assert resp.status_code in {400, 422}


def test_api_hybrid_search_success(client: TestClient) -> None:
    """Verify POST /api/v1/search/hybrid returns fused hybrid results."""
    mock_response = HybridSearchResponse(
        query="What are the supply chain risks?",
        retrieval_mode="hybrid",
        status="success",
        total_results=1,
        results=[
            HybridSearchResult(
                chunk_id="chk_01",
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_1A",
                section_title="Item 1A. Risk Factors",
                chunk_text="Supply chain text",
                source_url="https://sec.gov",
                dense_rank=1,
                dense_score=0.88,
                sparse_rank=1,
                bm25_score=14.5,
                rrf_score=0.0328,
                retrieval_sources=["dense", "sparse"],
            )
        ],
        diagnostics={
            "total_duration_seconds": 0.05,
            "dense_candidates_count": 1,
            "sparse_candidates_count": 1,
            "overlap_candidates_count": 1,
        },
    )

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._hybrid_search_service.search",
            return_value=mock_response,
        ),
    ):
        resp = client.post(
            "/api/v1/search/hybrid",
            json={
                "query": "What are the supply chain risks?",
                "ticker": "AAPL",
                "top_k": 5,
                "rrf_constant": 60,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["retrieval_mode"] == "hybrid"
        assert data["status"] == "success"
        assert data["total_results"] == 1
        item = data["results"][0]
        assert item["chunk_id"] == "chk_01"
        assert item["retrieval_sources"] == ["dense", "sparse"]
        assert item["rrf_score"] == 0.0328


def test_api_hybrid_search_empty_query(client: TestClient) -> None:
    """Verify POST /api/v1/search/hybrid returns 400 for empty query."""
    resp = client.post("/api/v1/search/hybrid", json={"query": ""})
    assert resp.status_code in {400, 422}


def test_api_bm25_stats_success(client: TestClient) -> None:
    """Verify GET /api/v1/index/bm25/stats."""
    mock_stats = BM25IndexStatsResponse(
        total_chunks=100,
        tokenizer_version="1.0.0",
        vocab_size=2500,
        avg_doc_len=450.5,
        index_location="datasets/indexes/bm25",
        last_updated_at="2026-11-15T20:00:00Z",
        indexed_tickers=["AAPL", "MSFT"],
    )

    with patch(
        "backend.api.routes._bm25_indexing_service.get_index_stats",
        return_value=mock_stats,
    ):
        resp = client.get("/api/v1/index/bm25/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_chunks"] == 100
        assert data["vocab_size"] == 2500
        assert "AAPL" in data["indexed_tickers"]
