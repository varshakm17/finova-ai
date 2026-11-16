"""Tests for FastAPI Evaluation Endpoints.

Validates:
- POST /api/v1/evaluations/run (triggers evaluation run across types)
- GET /api/v1/evaluations/{run_id} (retrieves run details and scorecards)
- GET /api/v1/evaluations (lists historical runs with filters)
- GET /api/v1/evaluations/{run_id}/cases (retrieves case results with filter)
- GET /api/v1/evaluations/benchmarks (retrieves benchmark metadata catalog)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_list_benchmark_datasets_endpoint() -> None:
    """Ensure benchmark datasets catalog is returned with expected metadata."""
    resp = client.get("/api/v1/evaluations/benchmarks")
    assert resp.status_code == 200
    benchmarks = resp.json()
    assert len(benchmarks) >= 4

    types = {b["benchmark_type"] for b in benchmarks}
    assert {"retrieval", "financial_calculation", "verification", "report"}.issubset(
        types
    )

    for b in benchmarks:
        assert "filename" in b
        assert "total_cases" in b
        assert b["total_cases"] > 0


def test_trigger_financial_calculation_run_endpoint() -> None:
    """Test triggering a financial calculation evaluation run via API."""
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"eval_type": "financial_calculation", "save_results": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert data["eval_type"] == "financial_calculation"
    assert data["status"] == "COMPLETED"
    assert data["passed_cases"] == data["total_cases"]

    run_id = data["run_id"]

    # Verify retrieval by run_id
    detail_resp = client.get(f"/api/v1/evaluations/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["run_id"] == run_id
    assert "summary" in detail
    assert "metrics" in detail

    # Verify retrieval of case results
    cases_resp = client.get(f"/api/v1/evaluations/{run_id}/cases")
    assert cases_resp.status_code == 200
    cases = cases_resp.json()
    assert len(cases) == data["total_cases"]


def test_trigger_verification_run_endpoint() -> None:
    """Test triggering an anti-hallucination verification evaluation run via API."""
    resp = client.post(
        "/api/v1/evaluations/run",
        json={"eval_type": "verification", "save_results": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["eval_type"] == "verification"
    assert "summary" in data
    ms = data["summary"].get("metrics_summary", {})
    assert ms.get("false_acceptance_rate") == 0.0


def test_list_evaluation_runs_endpoint() -> None:
    """Test listing historical evaluation runs with type filtering."""
    resp = client.get("/api/v1/evaluations?limit=10")
    assert resp.status_code == 200
    runs = resp.json()
    assert isinstance(runs, list)
    assert len(runs) > 0

    # Filter by financial_calculation
    filtered_resp = client.get(
        "/api/v1/evaluations?eval_type=financial_calculation&limit=5"
    )
    assert filtered_resp.status_code == 200
    filtered_runs = filtered_resp.json()
    assert all(r["eval_type"] == "financial_calculation" for r in filtered_runs)
