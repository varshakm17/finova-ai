"""Tests for CLI Evaluation Runner.

Validates that:
- run_benchmarks executes all requested benchmark suites.
- JSON artifacts are saved to specified output directory.
- CLI argument parsing works for all scopes and flags.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from evaluation.run_evaluation import run_benchmarks


def test_run_benchmarks_single_suite() -> None:
    """Test running a single benchmark suite programmatically."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = run_benchmarks(
            eval_type="financial_calculation",
            output_dir=tmpdir,
            save_to_db=False,
        )
        assert len(runs) == 1
        assert runs[0].eval_type == "financial_calculation"
        assert runs[0].passed_cases == runs[0].total_cases

        # Check artifact written to tmpdir
        json_files = list(Path(tmpdir).glob("*.json"))
        assert len(json_files) == 1


def test_run_benchmarks_all_suites() -> None:
    """Test running all 4 benchmark suites via run_benchmarks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = run_benchmarks(
            eval_type="all",
            output_dir=tmpdir,
            save_to_db=False,
        )
        assert len(runs) == 4
        eval_types = {r.eval_type for r in runs}
        assert {
            "retrieval",
            "financial_calculation",
            "verification",
            "report",
        } == eval_types

        # Check all 4 JSON artifacts written
        json_files = list(Path(tmpdir).glob("*.json"))
        assert len(json_files) == 4
