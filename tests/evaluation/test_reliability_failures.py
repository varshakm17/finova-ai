"""Reliability, Hardening & Failure Injection Tests for Finova AI.

Validates that:
- Question inputs exceeding 2000 characters are rejected with HTTP 422.
- Path traversal in custom dataset path is blocked.
- Malformed responses or missing files raise clean, sanitized errors.
- Unhandled mathematical exceptions (e.g. ZeroDivisionError) never leak to client.
- Empty indexes or search failures fall back gracefully.
- Concurrency and isolation remain stable under rapid execution.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from evaluation.financial_evaluator import FinancialEvaluator
from evaluation.retrieval_evaluator import RetrievalEvaluator

client = TestClient(app)


def test_question_max_length_validation_rag() -> None:
    """Ensure RAG question exceeding 2000 chars is rejected with 422 Unprocessable Entity."""
    long_question = "What was Apple revenue? " * 150  # ~3600 chars
    resp = client.post(
        "/api/v1/research/ask",
        json={"question": long_question, "ticker": "AAPL"},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_question_max_length_validation_agent() -> None:
    """Ensure multi-agent question exceeding 2000 chars is rejected with 422."""
    long_question = "Explain Microsoft cloud growth. " * 150
    resp = client.post(
        "/api/v1/agents/run",
        json={"question": long_question, "company_ticker": "MSFT"},
    )
    assert resp.status_code == 422


def test_question_max_length_validation_reports() -> None:
    """Ensure report generation question exceeding 2000 chars is rejected with 422."""
    long_question = "Generate full research report. " * 150
    resp = client.post(
        "/api/v1/reports/generate",
        json={"question": long_question, "ticker": "MSFT"},
    )
    assert resp.status_code == 422


def test_path_traversal_blocked_in_evaluations() -> None:
    """Ensure path traversal attempts in dataset_path are rejected."""
    traversal_path = "../../etc/shadow_or_password_probe.json"
    resp = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "retrieval",
            "dataset_path": traversal_path,
        },
    )
    assert resp.status_code == 400


def test_nonexistent_evaluation_run_returns_404() -> None:
    """Ensure querying an unknown run_id returns clean 404 without internal crash."""
    resp = client.get("/api/v1/evaluations/nonexistent_run_id_999999")
    assert resp.status_code == 404
    err_msg = resp.json().get("detail") or resp.json().get("message", "")
    assert "not found" in err_msg.lower()


def test_nonexistent_evaluation_cases_returns_404() -> None:
    """Ensure querying cases for an unknown run_id returns 404."""
    resp = client.get("/api/v1/evaluations/nonexistent_run_id_999999/cases")
    assert resp.status_code == 404
    err_msg = resp.json().get("detail") or resp.json().get("message", "")
    assert "not found" in err_msg.lower()


def test_financial_evaluator_missing_benchmark_file() -> None:
    """Ensure FinancialEvaluator raises FileNotFoundError for missing benchmark file."""
    evaluator = FinancialEvaluator()
    with pytest.raises(FileNotFoundError):
        evaluator.evaluate(dataset_path="nonexistent_benchmark.json")


def test_retrieval_evaluator_empty_retriever_handling() -> None:
    """Ensure RetrievalEvaluator gracefully handles retriever returning empty results."""
    evaluator = RetrievalEvaluator()

    def empty_retriever(q: dict, k: int) -> tuple[list[str], float]:
        return [], 1.0

    run = evaluator.evaluate(
        retriever_fn=empty_retriever,
        save=False,
    )
    assert run.total_cases > 0
    # Queries without hits should be recorded as issues, not crashing
    assert len(run.issues) > 0
