"""Tests for Pure Deterministic Financial Calculation Evaluator.

Validates that arithmetic computation:
- Uses 100% pure Python arithmetic (no LLM, no external paid APIs).
- Accurately computes ratios, margins, and cash flows against reference ground truth.
- Computes MAE, Max Error, and Percentage Error.
- Never crashes or silently converts zero denominators to zero.
- Gracefully returns unavailable status for missing required inputs.
- Persists execution scorecards and issues to SQLite.
"""

from __future__ import annotations

import tempfile

from backend.data.storage import Database
from evaluation.evaluation_models import EvaluationStatus, EvaluationType
from evaluation.financial_evaluator import FinancialEvaluator


def test_financial_evaluator_execution() -> None:
    """Test full financial calculation benchmark run."""
    evaluator = FinancialEvaluator()
    run = evaluator.evaluate(save=False)

    assert run.eval_type == EvaluationType.FINANCIAL_CALCULATION.value
    assert run.status == EvaluationStatus.COMPLETED.value
    assert run.total_cases >= 18
    assert run.passed_cases == run.total_cases, (
        "All deterministic calculations must pass"
    )
    assert run.summary.pass_rate == 1.0

    metrics = run.summary.metrics_summary
    assert "mean_absolute_error" in metrics
    assert metrics["mean_absolute_error"] < 0.001
    assert metrics["zero_denominator_accuracy"] == 1.0
    assert metrics["missing_input_accuracy"] == 1.0
    assert metrics["negative_value_accuracy"] == 1.0


def test_financial_evaluator_database_persistence() -> None:
    """Test persisting financial calculation evaluation results to SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    evaluator = FinancialEvaluator(db=db)
    run = evaluator.evaluate(save=True)

    saved_run = db.get_evaluation_run(run.run_id)
    assert saved_run is not None
    assert saved_run["run_id"] == run.run_id
    assert saved_run["eval_type"] == "financial_calculation"
    assert saved_run["passed_cases"] == run.total_cases

    cases = db.get_evaluation_case_results(run.run_id)
    assert len(cases) == run.total_cases
    assert all(c["passed"] for c in cases)

    metrics = db.get_evaluation_metrics(run.run_id)
    assert len(metrics) >= 5
    metric_names = {m["metric_name"] for m in metrics}
    assert "mean_absolute_error" in metric_names
    assert "zero_denominator_accuracy" in metric_names


def test_zero_denominator_not_silently_zeroed() -> None:
    """Ensure zero denominators result in status='unavailable' with None, never 0.0."""
    evaluator = FinancialEvaluator()
    val, status = evaluator._compute_metric(
        "gross_profit_margin",
        {"gross_profit": 50000.0, "revenue": 0.0},
    )
    # CalculationEngine raises ZeroDivisionError when revenue is 0
    # Evaluator catches it and returns None, "unavailable"
    assert val is None
    assert status == "unavailable"


def test_missing_inputs_graceful_handling() -> None:
    """Ensure omitted required inputs yield unavailable status without raising exception."""
    evaluator = FinancialEvaluator()
    val, status = evaluator._compute_metric(
        "operating_profit_margin",
        {"operating_income": 100000.0},  # missing revenue
    )
    assert val is None
    assert status == "unavailable"
