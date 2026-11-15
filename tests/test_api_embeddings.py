"""Integration tests for Semantic Embeddings & Vector Index API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.retrieval.retrieval_models import (
    EmbeddingStatusResponse,
    IndexingSummary,
    IndexStatsResponse,
    SemanticSearchResult,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_index_company_embeddings_success(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/embeddings/index triggers indexing."""
    mock_summary = IndexingSummary(
        ticker="AAPL",
        total_discovered=10,
        already_indexed=0,
        newly_indexed=10,
        updated_indexed=0,
        failed=0,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        backend="numpy",
        embedding_dimension=384,
        duration_seconds=1.23,
        message="Completed indexing for 'AAPL'.",
    )

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._indexing_service.index_company_chunks",
            return_value=mock_summary,
        ),
    ):
        resp = client.post("/api/v1/companies/AAPL/embeddings/index?force_reindex=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["total_discovered"] == 10
        assert data["newly_indexed"] == 10
        assert data["backend"] == "numpy"


def test_index_company_embeddings_not_found(client: TestClient) -> None:
    """Verify indexing returns 404 for unknown company ticker."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker", return_value=None
    ):
        resp = client.post("/api/v1/companies/NONEXISTENT/embeddings/index")
        assert resp.status_code == 404
        error_msg = resp.json().get("message") or resp.json().get("detail", "")
        assert "not found" in error_msg.lower()


def test_get_company_embedding_status_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/embeddings/status returns coverage metrics."""
    mock_status = EmbeddingStatusResponse(
        ticker="AAPL",
        total_available_chunks=14,
        indexed_chunks=14,
        pending_chunks=0,
        failed_chunks=0,
        active_model="sentence-transformers/all-MiniLM-L6-v2",
        active_vector_backend="numpy",
        embedding_dimension=384,
    )

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._indexing_service.get_indexing_status",
            return_value=mock_status,
        ),
    ):
        resp = client.get("/api/v1/companies/AAPL/embeddings/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["indexed_chunks"] == 14
        assert data["pending_chunks"] == 0
        assert data["embedding_dimension"] == 384


def test_get_company_embedding_status_not_found(client: TestClient) -> None:
    """Verify status returns 404 for unknown company ticker."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker", return_value=None
    ):
        resp = client.get("/api/v1/companies/NONEXISTENT/embeddings/status")
        assert resp.status_code == 404


def test_semantic_search_endpoint_success(client: TestClient) -> None:
    """Verify POST /api/v1/search/semantic returns ranked results."""
    mock_results = [
        SemanticSearchResult(
            chunk_id="aapl_10k_item1a_0",
            ticker="AAPL",
            company_name="Apple Inc.",
            cik="0000320193",
            filing_type="10-K",
            filing_date="2023-11-03",
            report_date="2023-09-30",
            accession_number="0000320193-23-000106",
            section_identifier="ITEM_1A",
            section_title="Item 1A. Risk Factors",
            chunk_text="Global supply chains present operational risks.",
            similarity_score=0.8921,
            source_url="https://sec.gov",
        )
    ]

    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker",
            return_value={"ticker": "AAPL"},
        ),
        patch(
            "backend.api.routes._semantic_search_service.search",
            return_value=mock_results,
        ),
    ):
        payload = {
            "query": "What are supply chain risks?",
            "ticker": "AAPL",
            "section_identifier": "ITEM_1A",
            "top_k": 3,
        }
        resp = client.post("/api/v1/search/semantic", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["chunk_id"] == "aapl_10k_item1a_0"
        assert data[0]["similarity_score"] == pytest.approx(0.8921)


def test_semantic_search_endpoint_empty_query(client: TestClient) -> None:
    """Verify empty query string is rejected with 422 or 400."""
    resp = client.post("/api/v1/search/semantic", json={"query": "   "})
    assert resp.status_code in {400, 422}


def test_semantic_search_endpoint_unknown_ticker(client: TestClient) -> None:
    """Verify semantic search with unknown ticker filter returns 404."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker", return_value=None
    ):
        payload = {"query": "valid query", "ticker": "UNKNOWN"}
        resp = client.post("/api/v1/search/semantic", json=payload)
        assert resp.status_code == 404


def test_get_vector_index_stats_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/index/stats returns index operational metadata."""
    mock_stats = IndexStatsResponse(
        active_backend="numpy",
        index_size=42,
        embedding_dimension=384,
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        index_location="storage://datasets/indexes",
        last_updated_at="2026-11-15T19:00:00Z",
        total_indexed_chunks=42,
    )

    with patch(
        "backend.api.routes._indexing_service.get_index_stats", return_value=mock_stats
    ):
        resp = client.get("/api/v1/index/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_backend"] == "numpy"
        assert data["index_size"] == 42
        assert data["index_location"] == "storage://datasets/indexes"
