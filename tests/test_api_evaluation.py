"""Integration tests for FastAPI Retrieval Evaluation and Evidence Quality endpoints.

Tests:
- POST /api/v1/evaluation/retrieval/run
- POST /api/v1/evaluation/retrieval/compare
- POST /api/v1/evaluation/evidence/validate
- GET /api/v1/evaluation/retrieval/reports/{report_id}
- GET /api/v1/retrieval/reranker/status
"""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_api_reranker_status() -> None:
    """Verify GET /api/v1/retrieval/reranker/status returns valid configuration."""
    response = client.get("/api/v1/retrieval/reranker/status")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "model_name" in data
    assert "device" in data
    assert data["device"] == "cpu"
    assert "initialized" in data
    assert "is_available" in data


def test_api_retrieval_evaluation_run() -> None:
    """Verify POST /api/v1/evaluation/retrieval/run executes evaluation over dataset."""
    payload = {
        "dataset_path": "datasets/evaluation/retrieval_queries.json",
        "retrieval_method": "sparse",
        "top_k": 3,
    }
    response = client.post("/api/v1/evaluation/retrieval/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "report_id" in data
    assert data["evaluation_method"] == "sparse"
    assert "metrics" in data
    assert "precision_at_k" in data["metrics"]
    assert "recall_at_k" in data["metrics"]
    assert "mrr" in data["metrics"]
    assert "map_score" in data["metrics"]
    assert "ndcg_at_k" in data["metrics"]
    assert "per_query_results" in data

    # Verify report can be retrieved by GET
    report_id = data["report_id"]
    get_rep = client.get(f"/api/v1/evaluation/retrieval/reports/{report_id}")
    assert get_rep.status_code == 200
    assert get_rep.json()["report_id"] == report_id


def test_api_retrieval_evaluation_run_missing_dataset() -> None:
    """Verify 404 returned when evaluation dataset path is invalid."""
    payload = {
        "dataset_path": "datasets/evaluation/non_existent.json",
        "retrieval_method": "hybrid",
    }
    response = client.post("/api/v1/evaluation/retrieval/run", json=payload)
    assert response.status_code == 404
    err_msg = response.json().get("detail") or response.json().get("message") or ""
    assert "not found" in err_msg.lower()


def test_api_retrieval_report_not_found() -> None:
    """Verify 404 returned when report_id does not exist."""
    response = client.get("/api/v1/evaluation/retrieval/reports/rep_nonexistent123")
    assert response.status_code == 404
    err_msg = response.json().get("detail") or response.json().get("message") or ""
    assert "not found" in err_msg.lower()


def test_api_retrieval_compare() -> None:
    """Verify POST /api/v1/evaluation/retrieval/compare executes multi-method benchmark."""
    payload = {
        "dataset_path": "datasets/evaluation/retrieval_queries.json",
        "top_k": 2,
        "include_reranking": False,
        "ticker_filter": "AAPL",
    }
    response = client.post("/api/v1/evaluation/retrieval/compare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "total_queries" in data
    assert data["total_queries"] > 0
    assert "method_summaries" in data
    assert "dense" in data["method_summaries"]
    assert "sparse" in data["method_summaries"]
    assert "hybrid" in data["method_summaries"]
    assert "hybrid_delta_vs_dense" in data
    assert "hybrid_delta_vs_sparse" in data
    assert "per_query_comparisons" in data


def test_api_evidence_validate_by_query() -> None:
    """Verify POST /api/v1/evaluation/evidence/validate with natural language query."""
    payload = {
        "query": "Supply chain risks and manufacturing dependencies",
        "retrieval_method": "sparse",
        "top_k": 3,
    }
    response = client.post("/api/v1/evaluation/evidence/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "total_chunks_inspected" in data
    assert "overall_status" in data
    assert "chunk_validations" in data
    assert "summary_notes" in data


def test_api_evidence_validate_by_chunk_ids() -> None:
    """Verify POST /api/v1/evaluation/evidence/validate with chunk IDs list."""
    payload = {
        "chunk_ids": ["test_chunk_001", "test_chunk_002"],
    }
    response = client.post("/api/v1/evaluation/evidence/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_chunks_inspected"] == 2
    assert len(data["chunk_validations"]) == 2
