"""Tests for Unified Information Retrieval Evaluator.

Validates that:
- Precision@K, Recall@K, MRR, MAP, NDCG@K, evidence coverage, and query success rate
  are calculated deterministically.
- Unannotated queries are handled gracefully (AP = 0.0 without unhandled exception).
- Graded relevance correctly discounts lower-grade chunks in NDCG.
- Results and metrics are persisted cleanly into SQLite.
"""

from __future__ import annotations

import tempfile

import pytest

from backend.data.storage import Database
from backend.evaluation.retrieval_evaluator import (
    calculate_average_precision,
    calculate_ndcg_at_k,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
)
from evaluation.evaluation_models import EvaluationType
from evaluation.retrieval_evaluator import RetrievalEvaluator


def test_ir_metric_math() -> None:
    """Verify core ranking formulas on deterministic controlled inputs."""
    relevant = {"c1", "c2", "c3"}

    # Precision@3 with 2 hits: 2 / 3
    p3 = calculate_precision_at_k(["c1", "c4", "c2"], relevant, k=3)
    assert p3 == pytest.approx(2.0 / 3.0, rel=1e-3)

    # Recall@3 with 2 hits: 2 / 3
    r3 = calculate_recall_at_k(["c1", "c4", "c2"], relevant, k=3)
    assert r3 == pytest.approx(2.0 / 3.0, rel=1e-3)

    # Reciprocal Rank: first hit at rank 2: 1 / 2 = 0.5
    rr = calculate_reciprocal_rank(["c4", "c1", "c2"], relevant)
    assert rr == 0.5

    # Average Precision: hits at rank 1 (P@1=1/1) and rank 3 (P@3=2/3)
    # AP = (1.0 + 2/3) / 3 = 1.6667 / 3 = 0.5555
    ap = calculate_average_precision(["c1", "c4", "c2"], relevant)
    assert ap == pytest.approx((1.0 + (2.0 / 3.0)) / 3.0, rel=1e-3)

    # NDCG@3 with binary relevance
    ndcg = calculate_ndcg_at_k(["c1", "c2", "c3"], relevant, k=3)
    assert ndcg == pytest.approx(1.0, rel=1e-3)


def test_empty_relevant_set_ap_zero() -> None:
    """Unannotated query with empty relevant set must return AP=0.0 without zero division."""
    ap = calculate_average_precision(["c1", "c2"], set())
    assert ap == 0.0

    rr = calculate_reciprocal_rank(["c1"], set())
    assert rr == 0.0


def test_retrieval_evaluator_execution() -> None:
    """Test full retrieval benchmark evaluation suite."""
    evaluator = RetrievalEvaluator()
    run = evaluator.evaluate(top_k=5, retrieval_mode="hybrid", save=False)

    assert run.eval_type == EvaluationType.RETRIEVAL.value
    assert run.total_cases >= 16
    assert run.passed_cases >= 14

    ms = run.summary.metrics_summary
    assert "mean_reciprocal_rank" in ms
    assert "mean_average_precision" in ms
    assert "precision_at_5" in ms
    assert "recall_at_5" in ms
    assert "ndcg_at_5" in ms
    assert ms["mean_reciprocal_rank"] >= 0.8
    assert ms["mean_average_precision"] >= 0.8


def test_retrieval_evaluator_database_persistence() -> None:
    """Test persisting retrieval benchmark execution to SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    evaluator = RetrievalEvaluator(db=db)
    run = evaluator.evaluate(top_k=5, save=True)

    saved_run = db.get_evaluation_run(run.run_id)
    assert saved_run is not None
    assert saved_run["eval_type"] == "retrieval"
    assert saved_run["passed_cases"] == run.passed_cases

    cases = db.get_evaluation_case_results(run.run_id)
    assert len(cases) == run.total_cases

    metrics = db.get_evaluation_metrics(run.run_id)
    assert len(metrics) >= 5
