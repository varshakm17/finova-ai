"""Tests for FastAPI endpoints in backend/api/routes.py."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.fixtures.sec_mock_data import (
    MOCK_COMPANY_FACTS_PAYLOAD,
    MOCK_SUBMISSIONS_PAYLOAD,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_search_company_endpoint_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/search returns company identification."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker"
    ) as mock_lookup:
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }

        response = client.get("/api/v1/companies/search?ticker=AAPL")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["cik"] == "0000320193"
        assert data["name"] == "Apple Inc."


def test_search_company_endpoint_missing_ticker(client: TestClient) -> None:
    """Verify GET /api/v1/companies/search returns 400 if ticker query param is missing."""
    response = client.get("/api/v1/companies/search")
    assert response.status_code == 400


def test_search_company_endpoint_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/companies/search returns 404 for unknown ticker."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker"
    ) as mock_lookup:
        mock_lookup.return_value = None

        response = client.get("/api/v1/companies/search?ticker=UNKNOWN99")
        assert response.status_code == 404


def test_get_company_metadata_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker} returns rich company metadata."""
    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker"
        ) as mock_lookup,
        patch("backend.api.routes.SECClient") as mock_client_cls,
    ):
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_sec_instance = MagicMock()
        mock_sec_instance.get_company_submissions.return_value = (
            MOCK_SUBMISSIONS_PAYLOAD
        )
        mock_client_cls.return_value = mock_sec_instance

        response = client.get("/api/v1/companies/AAPL")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["cik"] == "0000320193"
        assert data["sic"] == "3571"
        assert data["sic_description"] == "Electronic Computers"


def test_get_company_filings_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/filings returns filings list."""
    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker"
        ) as mock_lookup,
        patch("backend.api.routes.SECClient") as mock_client_cls,
    ):
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_sec_instance = MagicMock()
        mock_sec_instance.get_company_filings.return_value = [
            {
                "accession_number": "0000320193-23-000106",
                "cik": "0000320193",
                "form": "10-K",
                "filing_date": "2023-11-03",
                "report_date": "2023-09-30",
                "is_xbrl": True,
                "url": "http://sec.gov/10k",
            }
        ]
        mock_client_cls.return_value = mock_sec_instance

        response = client.get("/api/v1/companies/AAPL/filings?form_type=10-K")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["form"] == "10-K"
        assert data[0]["accession_number"] == "0000320193-23-000106"


def test_get_company_financials_and_specific_metric(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/financials and metric history."""
    with (
        patch(
            "backend.api.routes._company_service.get_company_by_ticker"
        ) as mock_lookup,
        patch("backend.api.routes.SECClient") as mock_client_cls,
    ):
        mock_lookup.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_sec_instance = MagicMock()
        mock_sec_instance.get_company_facts.return_value = MOCK_COMPANY_FACTS_PAYLOAD
        mock_client_cls.return_value = mock_sec_instance

        # 1. Fetch all financials
        response = client.get("/api/v1/companies/AAPL/financials")
        assert response.status_code == 200
        observations = response.json()
        assert len(observations) > 0

        # 2. Fetch specific metric
        rev_resp = client.get("/api/v1/companies/AAPL/financials/Revenue")
        assert rev_resp.status_code == 200
        rev_data = rev_resp.json()
        assert len(rev_data) > 0
        assert all(item["metric_name"] == "Revenue" for item in rev_data)

        # 3. Non-existent metric returns 404
        bad_metric_resp = client.get(
            "/api/v1/companies/AAPL/financials/NonExistentMetric"
        )
        assert bad_metric_resp.status_code == 404
