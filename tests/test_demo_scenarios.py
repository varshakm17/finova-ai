"""Tests for End-to-End Real Company Demonstration Scenarios."""

from __future__ import annotations

import tempfile

from evaluation.demo_scenarios.demo_integrity_auditor import (
    DemoIntegrityAuditor,
)
from evaluation.demo_scenarios.demo_scenarios import (
    DEMO_SCENARIOS,
    run_demo_scenario,
)


def test_demo_scenarios_definitions() -> None:
    """Verify all four demonstration scenario specifications exist with valid metadata."""
    expected_tickers = {"aapl", "msft", "tsla", "nvda"}
    assert set(DEMO_SCENARIOS.keys()) == expected_tickers

    for key, spec in DEMO_SCENARIOS.items():
        assert len(spec.ticker) >= 3
        assert len(spec.cik) == 10
        assert spec.accession_number != ""
        assert spec.sec_url.startswith("https://www.sec.gov/Archives/edgar/data/")
        assert len(spec.sections) >= 3
        assert len(spec.evidence_citations) >= 2
        assert len(spec.calculation_receipts) >= 2


def test_run_demo_scenario_execution() -> None:
    """Verify execution of a demo scenario generates valid Markdown and HTML artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = run_demo_scenario("aapl", output_dir=tmpdir, save_to_db=False)

        assert res.ticker == "AAPL"
        assert res.verification_status == "verified"
        assert res.sections_count >= 4
        assert res.markdown_path.exists()
        assert res.html_path.exists()

        # Check markdown content
        with open(res.markdown_path, encoding="utf-8") as f:
            md_text = f.read()
        assert "Apple Inc." in md_text
        assert "$383,285" in md_text
        assert "[E1]" in md_text
        assert "[C1]" in md_text

        # Check html content
        with open(res.html_path, encoding="utf-8") as f:
            html_text = f.read()
        assert "<!DOCTYPE html>" in html_text
        assert "Apple Inc." in html_text


def test_demo_integrity_auditor_all_scenarios() -> None:
    """Verify demo integrity auditor reports 100% pass rate across all 4 scenarios."""
    auditor = DemoIntegrityAuditor()
    report = auditor.audit_all(regenerate_if_missing=True)

    assert report.overall_status == "PASSED"
    assert report.total_scenarios == 4
    assert report.passed_scenarios == 4
    assert report.failed_scenarios == 0
    assert report.total_citations_checked >= 12
    assert report.total_receipts_checked >= 12

    for scenario_res in report.scenario_results:
        assert scenario_res.passed is True
        assert len(scenario_res.issues) == 0
        assert scenario_res.markdown_path.exists()
        assert scenario_res.html_path.exists()
