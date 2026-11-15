"""Integration tests for Financial Calculation API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.finance.calculation_models import (
    CalculationInputObservation,
    CalculationReceipt,
    CalculationSummaryResponse,
)
from backend.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def make_mock_receipt(
    metric_name: str = "gross_profit_margin",
    status: str = "calculated",
    val: float | None = 44.13,
) -> CalculationReceipt:
    """Helper generating synthetic CalculationReceipt."""
    return CalculationReceipt(
        calculation_id=f"0000320193_{metric_name}_annual_2023-09-30",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        metric_name=metric_name,
        calculated_value=val,
        unit="percentage",
        period_type="annual",
        period_start="2022-10-01",
        period_end="2023-09-30",
        fiscal_year=2023,
        fiscal_period="FY",
        formula_name=metric_name.replace("_", " ").title(),
        formula_expression="(Inputs) * 100",
        status=status,
        unavailable_reason=None
        if status == "calculated"
        else "Missing required inputs",
        inputs=[
            CalculationInputObservation(
                metric_name="Revenue",
                value=383285000000.0,
                unit="USD",
                period_end="2023-09-30",
                period_type="annual",
            )
        ],
    )


def test_post_calculations_endpoint_success(client: TestClient) -> None:
    """Verify POST /api/v1/companies/{ticker}/calculations triggers calculation and returns 200."""
    mock_summary = CalculationSummaryResponse(
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        period_type="annual",
        total_calculated=1,
        total_unavailable=0,
        total_invalid=0,
        calculations=[make_mock_receipt("gross_profit_margin")],
    )

    with patch(
        "backend.api.routes._calculation_service.calculate_company_metrics"
    ) as mock_calc:
        mock_calc.return_value = mock_summary

        response = client.post(
            "/api/v1/companies/AAPL/calculations",
            json={"start_year": 2022, "end_year": 2023, "period_type": "annual"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["total_calculated"] == 1
        assert len(data["calculations"]) == 1
        assert data["calculations"][0]["metric_name"] == "gross_profit_margin"


def test_post_calculations_invalid_period_type(client: TestClient) -> None:
    """Verify POST returns 400 if period_type is invalid."""
    response = client.post(
        "/api/v1/companies/AAPL/calculations",
        json={"period_type": "invalid_period"},
    )
    assert response.status_code == 400
    assert "Invalid period_type" in response.json()["message"]


def test_post_calculations_unsupported_metric(client: TestClient) -> None:
    """Verify POST returns 400 if metric is unsupported."""
    response = client.post(
        "/api/v1/companies/AAPL/calculations",
        json={"metrics": ["unsupported_fake_metric"]},
    )
    assert response.status_code == 400
    assert "Unsupported metric(s)" in response.json()["message"]


def test_post_calculations_company_not_found(client: TestClient) -> None:
    """Verify POST returns 404 if company is not found."""
    with patch(
        "backend.api.routes._calculation_service.calculate_company_metrics"
    ) as mock_calc:
        mock_calc.side_effect = ValueError("Company with ticker 'UNKNOWN' not found.")

        response = client.post("/api/v1/companies/UNKNOWN/calculations")
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()


def test_get_calculations_list_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/calculations returns list of receipts."""
    mock_receipt = make_mock_receipt("operating_profit_margin").model_dump()

    with (
        patch("backend.api.routes._company_service.get_company_by_ticker") as mock_comp,
        patch("backend.api.routes._db.get_financial_calculations") as mock_db_get,
    ):
        mock_comp.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_db_get.return_value = [mock_receipt]

        response = client.get("/api/v1/companies/AAPL/calculations?period_type=annual")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["metric_name"] == "operating_profit_margin"


def test_get_calculations_list_company_not_found(client: TestClient) -> None:
    """Verify GET returns 404 for unknown company."""
    with patch(
        "backend.api.routes._company_service.get_company_by_ticker"
    ) as mock_comp:
        mock_comp.return_value = None

        response = client.get("/api/v1/companies/UNKNOWN/calculations")
        assert response.status_code == 404


def test_get_specific_metric_history_success(client: TestClient) -> None:
    """Verify GET /api/v1/companies/{ticker}/calculations/{metric_name} returns history."""
    mock_receipt = make_mock_receipt("free_cash_flow", val=99584000000.0).model_dump()

    with (
        patch("backend.api.routes._company_service.get_company_by_ticker") as mock_comp,
        patch("backend.api.routes._db.get_financial_calculations") as mock_db_get,
    ):
        mock_comp.return_value = {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
        }
        mock_db_get.return_value = [mock_receipt]

        response = client.get("/api/v1/companies/AAPL/calculations/free_cash_flow")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["metric_name"] == "free_cash_flow"


def test_get_specific_metric_invalid_name(client: TestClient) -> None:
    """Verify GET returns 400 for unapproved metric name."""
    response = client.get("/api/v1/companies/AAPL/calculations/non_existent_metric")
    assert response.status_code == 400
    assert "not recognized" in response.json()["message"]


def test_get_calculation_by_id_success(client: TestClient) -> None:
    """Verify GET /api/v1/calculations/{id} returns single receipt."""
    receipt = make_mock_receipt("current_ratio", val=1.45).model_dump()

    with patch("backend.api.routes._db.get_financial_calculation_by_id") as mock_get_id:
        mock_get_id.return_value = receipt

        response = client.get("/api/v1/calculations/calc-12345")
        assert response.status_code == 200
        data = response.json()
        assert data["metric_name"] == "current_ratio"
        assert data["calculated_value"] == 1.45


def test_get_calculation_by_id_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/calculations/{id} returns 404 when ID does not exist."""
    with patch("backend.api.routes._db.get_financial_calculation_by_id") as mock_get_id:
        mock_get_id.return_value = None

        response = client.get("/api/v1/calculations/non-existent-id")
        assert response.status_code == 404
        assert "not found" in response.json()["message"].lower()
