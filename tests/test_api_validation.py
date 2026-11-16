"""Comprehensive API Contract & Validation Test Suite for Finova AI.

Validates:
- Health and subsystem diagnostics.
- Error codes on invalid inputs and non-existent IDs.
- Edge case handling across calculations, retrieval, reports, and verification.
- Schema compliance and structured error responses.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_api_root_info(client: TestClient) -> None:
    """Verify GET / returns API metadata and documentation links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["documentation"] == "/docs"
    assert data["health_check"] == "/health"


def test_api_health_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/health returns subsystem statuses and masked config."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"].lower() in ("healthy", "degraded")
    assert "subsystems" in data
    assert "database" in data["subsystems"]
    assert "sec_client" in data["subsystems"]
    assert "config" in data
    assert data["subsystems"]["database"]["status"].lower() in ("healthy", "degraded")


def test_company_search_invalid_ticker(client: TestClient) -> None:
    """Verify GET /api/v1/companies/search rejects empty or missing tickers."""
    # Missing ticker
    res_missing = client.get("/api/v1/companies/search")
    assert res_missing.status_code == 400

    # Whitespace ticker
    res_empty = client.get("/api/v1/companies/search?ticker=   ")
    assert res_empty.status_code in (400, 404)


def test_get_report_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/reports/{report_id} returns 404 for non-existent report."""
    response = client.get("/api/v1/reports/rep_non_existent_123456789")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data.get("detail", data.get("message", "")).lower()


def test_verify_report_not_found(client: TestClient) -> None:
    """Verify POST /api/v1/reports/{report_id}/verify returns 404 for non-existent report."""
    response = client.post("/api/v1/reports/rep_non_existent_123456789/verify")
    assert response.status_code == 404


def test_export_report_markdown_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/reports/{report_id}/export/markdown returns 404."""
    response = client.get("/api/v1/reports/rep_non_existent_123456789/export/markdown")
    assert response.status_code == 404


def test_export_report_html_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/reports/{report_id}/export/html returns 404."""
    response = client.get("/api/v1/reports/rep_non_existent_123456789/export/html")
    assert response.status_code == 404


def test_trigger_calculation_invalid_ticker(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/calculations handles invalid ticker."""
    response = client.post(
        "/api/v1/companies/NONEXISTENT99/calculations",
        json={"metrics": ["gross_profit_margin"]},
    )
    assert response.status_code in (200, 404)


def test_rag_research_missing_question(client: TestClient) -> None:
    """Verify POST /api/v1/research/ask rejects payload without research question."""
    response = client.post(
        "/api/v1/research/ask",
        json={"ticker": "AAPL"},  # missing question
    )
    assert response.status_code == 422


def test_agent_run_invalid_empty_body(client: TestClient) -> None:
    """Verify POST /api/v1/agents/run rejects empty JSON body."""
    response = client.post("/api/v1/agents/run", json={})
    assert response.status_code == 422


def test_retrieval_evaluation_invalid_dataset(client: TestClient) -> None:
    """Verify POST /api/v1/evaluation/retrieval/run rejects non-existent dataset file."""
    response = client.post(
        "/api/v1/evaluation/retrieval/run",
        json={"dataset_path": "datasets/non_existent_dataset_123.json"},
    )
    assert response.status_code in (400, 404, 422)
