"""Tests for Anti-Hallucination & Claim Verification Evaluator.

Validates that:
- False Acceptance Rate (FAR) is minimized (targeting 0.0% ungrounded claim leakage).
- Confusion matrix correctly identifies True Positives, False Positives, True Negatives, False Negatives.
- Unsupported and contradicted claims are flagged deterministically.
- Mismatched periods, numeric scale errors, and cross-company attributions trigger rejections.
"""

from __future__ import annotations

import tempfile

from backend.data.storage import Database
from evaluation.evaluation_models import EvaluationType
from evaluation.verification_evaluator import VerificationEvaluator


def test_verification_evaluator_execution() -> None:
    """Test full verification benchmark execution."""
    evaluator = VerificationEvaluator()
    run = evaluator.evaluate(save=False)

    assert run.eval_type == EvaluationType.VERIFICATION.value
    assert run.total_cases >= 18
    assert run.passed_cases >= 16

    ms = run.summary.metrics_summary
    assert "precision" in ms
    assert "recall" in ms
    assert "false_acceptance_rate" in ms
    assert "false_rejection_rate" in ms
    assert "unsupported_detection_rate" in ms
    assert "contradicted_detection_rate" in ms

    # False Acceptance Rate must be 0.0% (strict zero-tolerance for ungrounded assertions)
    assert ms["false_acceptance_rate"] == 0.0, (
        "Zero ungrounded assertions must be accepted"
    )
    assert ms["unsupported_detection_rate"] == 1.0, (
        "All unsupported assertions must be flagged"
    )
    assert ms["contradicted_detection_rate"] == 1.0, (
        "All contradicted assertions must be flagged"
    )


def test_verification_evaluator_database_persistence() -> None:
    """Test persisting verification benchmark run, case results, and confusion metrics to SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    evaluator = VerificationEvaluator(db=db)
    run = evaluator.evaluate(save=True)

    saved_run = db.get_evaluation_run(run.run_id)
    assert saved_run is not None
    assert saved_run["run_id"] == run.run_id
    assert saved_run["eval_type"] == "verification"

    cases = db.get_evaluation_case_results(run.run_id)
    assert len(cases) == run.total_cases

    metrics = db.get_evaluation_metrics(run.run_id)
    assert len(metrics) >= 5
    m_names = {m["metric_name"] for m in metrics}
    assert "false_acceptance_rate" in m_names
    assert "precision" in m_names
