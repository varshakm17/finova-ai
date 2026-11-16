"""Tests for Evaluation Benchmark Datasets.

Validates JSON schema, mandatory fields, edge-case coverage, and provenance tracking
across retrieval, financial calculations, verification, and report benchmarks.
"""

from __future__ import annotations

import json
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent / "evaluation" / "datasets"


def test_retrieval_benchmark_schema() -> None:
    """Validate schema and contents of retrieval_benchmark.json."""
    path = DATASETS_DIR / "retrieval_benchmark.json"
    assert path.exists(), f"Missing dataset: {path}"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "queries" in data
    meta = data["metadata"]
    assert meta["benchmark_name"] == "finova_retrieval_benchmark"
    assert meta["total_queries"] >= 16

    queries = data["queries"]
    assert len(queries) >= 16

    categories = set()
    companies = set()
    for q in queries:
        assert "query_id" in q
        assert "research_question" in q
        assert "company_ticker" in q
        assert "expected_filing_type" in q
        assert "expected_section" in q
        assert "dataset_provenance" in q
        categories.add(q.get("category"))
        companies.add(q.get("company_ticker"))

    # Verify coverage across canonical categories
    assert {"overview", "revenue", "margins", "risk_factors", "mda"}.issubset(
        categories
    )
    assert {"AAPL", "MSFT", "TSLA", "NVDA"}.issubset(companies)


def test_financial_calculation_benchmark_schema() -> None:
    """Validate schema and edge case conditions in financial_calculation_benchmark.json."""
    path = DATASETS_DIR / "financial_calculation_benchmark.json"
    assert path.exists(), f"Missing dataset: {path}"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "cases" in data
    cases = data["cases"]
    assert len(cases) >= 18

    scenarios = set()
    metrics = set()
    zero_denom_found = False
    missing_inputs_found = False
    negative_values_found = False

    for c in cases:
        assert "case_id" in c
        assert "metric_name" in c
        assert "inputs" in c
        assert "expected_status" in c
        assert "dataset_provenance" in c
        scenarios.add(c.get("test_scenario"))
        metrics.add(c.get("metric_name"))

        if c.get("test_scenario") == "zero_denominator":
            zero_denom_found = True
            assert c["expected_status"] == "unavailable"
            assert c["expected_value"] is None
        elif c.get("test_scenario") == "missing_inputs":
            missing_inputs_found = True
            assert c["expected_status"] == "unavailable"
            assert c["expected_value"] is None
        elif c.get("test_scenario") == "negative_values":
            negative_values_found = True
            assert c["expected_value"] < 0

    assert zero_denom_found, "Benchmark must contain zero-denominator test cases"
    assert missing_inputs_found, "Benchmark must contain missing input test cases"
    assert negative_values_found, "Benchmark must contain negative value test cases"
    assert len(metrics) >= 8, "Must cover at least 8 canonical financial metrics"


def test_verification_benchmark_schema() -> None:
    """Validate verification benchmark claim types, verdicts, and failure types."""
    path = DATASETS_DIR / "verification_benchmark.json"
    assert path.exists(), f"Missing dataset: {path}"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "cases" in data
    cases = data["cases"]
    assert len(cases) >= 18

    verdicts = set()
    failure_types = set()
    grounded_count = 0
    ungrounded_count = 0

    for c in cases:
        assert "case_id" in c
        assert "claim_text" in c
        assert "expected_verdict" in c
        assert "is_grounded" in c
        assert "failure_type" in c
        verdicts.add(c["expected_verdict"])
        failure_types.add(c["failure_type"])

        if c["is_grounded"]:
            grounded_count += 1
        else:
            ungrounded_count += 1

    assert "supported" in verdicts
    assert "unsupported" in verdicts
    assert "contradicted" in verdicts
    assert grounded_count >= 5, "Must include grounded assertions"
    assert ungrounded_count >= 10, "Must include negative probe assertions"
    assert "numeric_mismatch" in failure_types
    assert "period_mismatch" in failure_types
    assert "fabricated_citation" in failure_types
    assert "wrong_company" in failure_types


def test_report_benchmark_schema() -> None:
    """Validate multi-section report scenarios and canonical section expectations."""
    path = DATASETS_DIR / "report_benchmark.json"
    assert path.exists(), f"Missing dataset: {path}"

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "scenarios" in data
    scenarios = data["scenarios"]
    assert len(scenarios) >= 8

    for sc in scenarios:
        assert "scenario_id" in sc
        assert "title" in sc
        assert "request" in sc
        assert "expected_status" in sc
        assert "expected_canonical_sections" in sc
        assert "min_required_citations" in sc
        assert len(sc["expected_canonical_sections"]) >= 2
