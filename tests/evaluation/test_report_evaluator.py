"""Tests for Multi-Section Financial Research Report Evaluator.

Validates that:
- All 8 canonical report sections are audited for coverage.
- Citation integrity, structured tables, and limitation disclosures are enforced.
- Missing sections or citation deficits generate diagnostic issues.
- Overall quality index reflects composite fulfillment.
"""

from __future__ import annotations

import tempfile

from backend.agents.agent_models import (
    FinancialResearchReport,
    ReportSection,
    WorkflowStatus,
)
from backend.data.storage import Database
from evaluation.evaluation_models import EvaluationType
from evaluation.report_evaluator import ReportEvaluator


def test_report_evaluator_execution() -> None:
    """Test full report benchmark evaluation suite."""
    evaluator = ReportEvaluator()
    run = evaluator.evaluate(save=False)

    assert run.eval_type == EvaluationType.REPORT.value
    assert run.total_cases >= 8
    assert run.passed_cases >= 7

    ms = run.summary.metrics_summary
    assert "section_coverage_rate" in ms
    assert "citation_coverage_rate" in ms
    assert "overall_quality_score" in ms
    assert ms["section_coverage_rate"] >= 0.85
    assert ms["overall_quality_score"] >= 0.85


def test_report_evaluator_flags_missing_sections() -> None:
    """Ensure report missing canonical sections is flagged with issues."""
    evaluator = ReportEvaluator()

    # Generator providing incomplete report (only 1 section)
    def incomplete_generator(scenario: dict) -> FinancialResearchReport:
        return FinancialResearchReport(
            request_id="req_test",
            company_name="Test Co",
            ticker="TST",
            title="Incomplete Report",
            status=WorkflowStatus.COMPLETED.value,
            markdown_content="# Incomplete",
            sections=[
                ReportSection(
                    section_key="executive_summary",
                    title="Executive Summary",
                    content_markdown="Summary only",
                )
            ],
            references=[],
        )

    run = evaluator.evaluate(report_generator_fn=incomplete_generator, save=False)
    assert run.failed_cases > 0
    assert len(run.issues) > 0
    missing_sec_issues = [
        i for i in run.issues if i.issue_type == "missing_canonical_sections"
    ]
    assert len(missing_sec_issues) > 0


def test_report_evaluator_database_persistence() -> None:
    """Test persisting report evaluation results to SQLite."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = Database(db_path=db_path)
    evaluator = ReportEvaluator(db=db)
    run = evaluator.evaluate(save=True)

    saved_run = db.get_evaluation_run(run.run_id)
    assert saved_run is not None
    assert saved_run["eval_type"] == "report"

    cases = db.get_evaluation_case_results(run.run_id)
    assert len(cases) == run.total_cases
