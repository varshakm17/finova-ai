"""Tests for Performance Smoke Test Suite."""

from __future__ import annotations

from evaluation.performance_smoke_tests import PerformanceSmokeTester


def test_performance_smoke_tester_execution() -> None:
    """Verify performance smoke test executes and captures environment and metrics."""
    tester = PerformanceSmokeTester()
    report = tester.run_all(iterations=2)

    assert report.environment["python_version"].startswith("3.11")
    assert report.environment["device"] == "cpu"
    assert len(report.measurements) >= 5

    op_names = {m.operation_name for m in report.measurements}
    assert "backend_app_creation" in op_names
    assert "get_health_endpoint" in op_names
    assert "deterministic_margin_calculation" in op_names
    assert "sqlite_upsert_read_transaction" in op_names

    for m in report.measurements:
        assert m.mean_latency_ms >= 0.0
        assert m.p95_latency_ms >= 0.0

