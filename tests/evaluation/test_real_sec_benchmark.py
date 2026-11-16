"""Tests for the Real-World SEC Benchmark Dataset and Validator.

Validates that:
- `real_sec_benchmark.json` satisfies statutory SEC EDGAR formatting rules.
- Accession numbers follow SEC 10-2-6 syntax.
- CIK-to-ticker mappings match Apple, Microsoft, Tesla, and NVIDIA filings.
- The benchmark validator properly classifies validated vs pending queries.
- Retrieval evaluation on real SEC filings correctly isolates pending annotations
  from aggregate certified scorecards.
"""

from __future__ import annotations

import json

from evaluation.evaluation_models import EvaluationType
from evaluation.real_sec_benchmark_validator import (
    RealSECBenchmarkValidator,
)
from evaluation.retrieval_evaluator import (
    REAL_SEC_BENCHMARK_PATH,
    RetrievalEvaluator,
)


def test_real_sec_benchmark_file_exists() -> None:
    """Verify that the real SEC benchmark dataset JSON file exists."""
    assert REAL_SEC_BENCHMARK_PATH.exists()


def test_real_sec_benchmark_schema_and_metadata() -> None:
    """Verify metadata structure, query counts, and company coverage."""
    with open(REAL_SEC_BENCHMARK_PATH, encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("metadata", {})
    assert meta.get("benchmark_name") == "finova_real_sec_benchmark"
    assert meta.get("total_queries") == 24
    assert meta.get("validated_queries") == 20
    assert meta.get("pending_queries") == 4
    assert set(meta.get("companies", [])) == {"AAPL", "MSFT", "TSLA", "NVDA"}

    queries = data.get("queries", [])
    assert len(queries) == 24


def test_real_sec_benchmark_validator_execution() -> None:
    """Verify that the benchmark validator passes the curated dataset."""
    validator = RealSECBenchmarkValidator()
    report = validator.validate_file(REAL_SEC_BENCHMARK_PATH)

    assert report.total_queries == 24
    assert report.validated_filings == 20
    assert report.pending_annotations == 4
    assert report.invalid_metadata_count == 0
    assert report.missing_source_count == 0
    assert report.is_dataset_valid is True
    assert len(report.errors) == 0


def test_real_sec_benchmark_validator_detects_invalid_data() -> None:
    """Verify validator catches corrupted accession numbers and CIK mismatches."""
    validator = RealSECBenchmarkValidator()
    bad_queries = [
        {
            "query_id": "BAD-001",
            "company_ticker": "AAPL",
            "cik": "0000999999",  # Wrong CIK for Apple
            "accession_number": "0000320193-23-000106",
            "sec_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm",
            "ground_truth_excerpt": "Valid excerpt text.",
            "status": "validated_real_filing",
        },
        {
            "query_id": "BAD-002",
            "company_ticker": "MSFT",
            "cik": "0000789019",
            "accession_number": "invalid-accession-syntax",  # Malformed
            "sec_url": "https://www.sec.gov/Archives/edgar/data/789019/000078901923000085/msft-20230630.htm",
            "ground_truth_excerpt": "Valid excerpt text.",
            "status": "validated_real_filing",
        },
    ]

    report = validator.validate_queries(bad_queries)
    assert report.is_dataset_valid is False
    assert report.invalid_metadata_count == 2
    assert len(report.errors) >= 2


def test_retrieval_evaluator_real_sec_dataset() -> None:
    """Verify retrieval evaluation on the real SEC dataset isolates pending queries."""
    evaluator = RetrievalEvaluator()
    run = evaluator.evaluate(dataset_path="real_sec", top_k=5, save=False)

    assert run.eval_type == EvaluationType.RETRIEVAL.value
    assert run.total_cases == 24
    # All 20 certified cases pass
    assert run.passed_cases == 20
    assert run.summary.pass_rate == 1.0

    ms = run.summary.metrics_summary
    assert ms["validated_cases"] == 20
    assert ms["pending_cases"] == 4
    assert ms["dataset_type"] == "real_sec"
    assert "by_company" in ms
    assert set(ms["by_company"].keys()) == {"AAPL", "MSFT", "TSLA", "NVDA"}

    # Verify each company has 5 validated cases
    for comp in ["AAPL", "MSFT", "TSLA", "NVDA"]:
        assert ms["by_company"][comp]["validated_cases"] == 5
        assert ms["by_company"][comp]["success_rate"] == 1.0
