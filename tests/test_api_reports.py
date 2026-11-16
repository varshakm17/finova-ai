"""Tests for Financial Research Reports FastAPI Endpoints (Session 11).

Validates API routes for report generation, report retrieval, verification audits,
and historical listing using TestClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.agents.agent_models import (
    ReportGenerationResponse,
)
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_generate_report(client: TestClient) -> None:
    """Test POST /api/v1/reports/generate endpoint."""
    mock_response = ReportGenerationResponse(
        request_id="req_test_01",
        report_id="rep_test_01",
        status="completed",
        verification_status="VERIFIED",
        plan_summary="Executed 4 tasks.",
        markdown_content="# Report: Apple Inc.\n\nSummary...",
        html_content="<!DOCTYPE html><html><body><h1>Report</h1></body></html>",
        total_sections=7,
        total_evidence_cited=2,
        total_calculations_cited=3,
        execution_time_ms=1200.0,
    )

    with patch("backend.api.routes.get_orchestration_engine") as mock_engine_getter:
        mock_engine = MagicMock()
        mock_engine.run_report.return_value = mock_response
        mock_engine_getter.return_value = mock_engine

        resp = client.post(
            "/api/v1/reports/generate",
            json={
                "question": "Analyze Apple financial performance and profitability in FY2023.",
                "ticker": "AAPL",
                "reporting_period": "FY2023",
                "output_format": "markdown",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == "rep_test_01"
        assert data["status"] == "completed"
        assert data["verification_status"] == "VERIFIED"
        assert data["total_sections"] == 7


def test_api_get_report_by_id(client: TestClient) -> None:
    """Test GET /api/v1/reports/{report_id} endpoint."""
    mock_rep = {
        "report_id": "rep_123",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "title": "Financial Brief: Apple Inc.",
        "status": "completed",
        "verification_status": "VERIFIED",
        "markdown_content": "# Report...",
        "sections": [
            {
                "section_id": "s1",
                "section_key": "executive_summary",
                "title": "Executive Summary",
                "order_index": 1,
                "content_markdown": "Summary...",
            }
        ],
        "references": [],
    }

    with patch("backend.api.routes._db.get_research_report") as mock_get:
        mock_get.return_value = mock_rep
        resp = client.get("/api/v1/reports/rep_123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == "rep_123"
        assert data["ticker"] == "AAPL"


def test_api_get_report_404(client: TestClient) -> None:
    """Test GET /api/v1/reports/{report_id} returns 404 for nonexistent report."""
    with patch("backend.api.routes._db.get_research_report") as mock_get:
        mock_get.return_value = None
        resp = client.get("/api/v1/reports/nonexistent_id")
        assert resp.status_code == 404
        data = resp.json()
        detail = data.get("detail") or data.get("message", "")
        assert "not found" in detail.lower()


def test_api_get_report_verification(client: TestClient) -> None:
    """Test GET /api/v1/reports/{report_id}/verification endpoint."""
    mock_rep = {
        "report_id": "rep_123",
        "verification_status": "VERIFIED",
        "status": "completed",
    }
    with patch("backend.api.routes._db.get_research_report") as mock_get_rep:
        with patch("backend.api.routes._db.get_verification_run") as mock_get_v:
            mock_get_rep.return_value = mock_rep
            mock_get_v.return_value = {
                "overall_status": "VERIFIED",
                "supported_claims": 5,
                "contradicted_claims": 0,
            }

            resp = client.get("/api/v1/reports/rep_123/verification")
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "VERIFIED"
            assert data["supported_claims"] == 5


def test_api_list_reports(client: TestClient) -> None:
    """Test GET /api/v1/reports listing endpoint."""
    mock_list = [
        {"report_id": "rep_1", "ticker": "AAPL", "title": "Apple Brief"},
        {"report_id": "rep_2", "ticker": "MSFT", "title": "Microsoft Brief"},
    ]
    with patch("backend.api.routes._db.list_research_reports") as mock_list_db:
        mock_list_db.return_value = mock_list
        resp = client.get("/api/v1/reports?ticker=AAPL")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
