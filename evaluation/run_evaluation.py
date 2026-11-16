"""Command-Line Evaluation & Benchmarking Runner for Finova AI.

Executes deterministic offline evaluation across Information Retrieval, Pure Financial Math,
Anti-Hallucination Verification, and Autonomous Research Report Generation.

Usage:
    python -m evaluation.run_evaluation --eval-type all
    python -m evaluation.run_evaluation --eval-type financial_calculation
    python -m evaluation.run_evaluation --eval-type verification
    python -m evaluation.run_evaluation --eval-type retrieval --top-k 5 --retrieval-mode hybrid
    python -m evaluation.run_evaluation --eval-type report
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from backend.data.storage import Database
from backend.utils.logger import get_logger
from evaluation.evaluation_models import EvaluationRun, EvaluationType
from evaluation.financial_evaluator import FinancialEvaluator
from evaluation.report_evaluator import ReportEvaluator
from evaluation.retrieval_evaluator import RetrievalEvaluator
from evaluation.verification_evaluator import VerificationEvaluator

logger = get_logger("run_evaluation")


def run_benchmarks(
    eval_type: str = "all",
    dataset_path: str | None = None,
    top_k: int = 5,
    retrieval_mode: str = "hybrid",
    output_dir: str | None = None,
    save_to_db: bool = True,
) -> list[EvaluationRun]:
    """Execute evaluation suites based on CLI request.

    Args:
        eval_type: 'all', 'retrieval', 'financial_calculation', 'verification', or 'report'.
        dataset_path: Optional custom path to a benchmark dataset file.
        top_k: Top-K ranking cutoff for retrieval metrics.
        retrieval_mode: Retrieval modality for search evaluation.
        output_dir: Directory to save JSON benchmark output artifacts.
        save_to_db: Whether to write results to SQLite evaluation tables.

    Returns:
        List of completed EvaluationRun objects.
    """
    db = Database()
    runs: list[EvaluationRun] = []
    out_path = Path(output_dir) if output_dir else Path("evaluation/results")
    out_path.mkdir(parents=True, exist_ok=True)

    target_types: list[str]
    if eval_type == "all":
        target_types = [
            EvaluationType.RETRIEVAL.value,
            EvaluationType.FINANCIAL_CALCULATION.value,
            EvaluationType.VERIFICATION.value,
            EvaluationType.REPORT.value,
        ]
    else:
        target_types = [eval_type]

    for t in target_types:
        print("\n=======================================================")
        print(f"  RUNNING BENCHMARK: {t.upper()}")
        print("=======================================================")

        if t == EvaluationType.RETRIEVAL.value:
            evaluator = RetrievalEvaluator(db=db)
            run = evaluator.evaluate(
                dataset_path=dataset_path,
                top_k=top_k,
                retrieval_mode=retrieval_mode,
                save=save_to_db,
            )
        elif t == EvaluationType.FINANCIAL_CALCULATION.value:
            evaluator = FinancialEvaluator(db=db)
            run = evaluator.evaluate(
                dataset_path=dataset_path,
                save=save_to_db,
            )
        elif t == EvaluationType.VERIFICATION.value:
            evaluator = VerificationEvaluator(db=db)
            run = evaluator.evaluate(
                dataset_path=dataset_path,
                save=save_to_db,
            )
        elif t == EvaluationType.REPORT.value:
            evaluator = ReportEvaluator(db=db)
            run = evaluator.evaluate(
                dataset_path=dataset_path,
                save=save_to_db,
            )
        else:
            print(f"Unknown evaluation type: {t}")
            continue

        runs.append(run)

        # Print Scorecard
        _print_run_scorecard(run)

        # Export artifact JSON
        artifact_file = out_path / f"{run.eval_type}_{run.run_id}.json"
        with open(artifact_file, "w", encoding="utf-8") as f:
            f.write(run.model_dump_json(indent=2))
        print(f"\nSaved benchmark run artifact: {artifact_file}")

    return runs


def _print_run_scorecard(run: EvaluationRun) -> None:
    """Print clean terminal scorecard table."""
    print(f"\n--- EVALUATION SCORECARD: {run.eval_type.upper()} ---")
    print(f"Run ID:      {run.run_id}")
    print(f"Total Cases: {run.total_cases}")
    print(f"Passed:      {run.passed_cases}")
    print(f"Failed:      {run.failed_cases}")
    print(f"Pass Rate:   {run.summary.pass_rate * 100.0:.2f}%")
    print(f"Duration:    {run.duration_ms:.2f} ms")
    print("\nMetrics Summary:")
    for k, v in run.summary.metrics_summary.items():
        if isinstance(v, float):
            print(f"  - {k:<30}: {v:.4f}")
        else:
            print(f"  - {k:<30}: {v}")

    if run.issues:
        print(f"\nDiagnostic Issues ({len(run.issues)} total):")
        for iss in run.issues[:5]:
            print(f"  [{iss.severity}] {iss.case_id or 'General'}: {iss.description}")
        if len(run.issues) > 5:
            print(f"  ... and {len(run.issues) - 5} more issues.")


def main() -> None:
    """Entry point for CLI evaluation runner."""
    parser = argparse.ArgumentParser(
        description="Finova AI End-to-End Evaluation & Benchmarking Runner"
    )
    parser.add_argument(
        "--eval-type",
        choices=["all", "retrieval", "financial_calculation", "verification", "report"],
        default="all",
        help="Type of evaluation to run (default: all)",
    )
    parser.add_argument(
        "--dataset-path",
        type=str,
        default=None,
        help="Optional path to custom benchmark dataset file",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-K ranking cutoff for retrieval metrics (default: 5)",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=["dense", "sparse", "hybrid", "reranked"],
        default="hybrid",
        help="Retrieval mode for search benchmarks (default: hybrid)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="evaluation/results",
        help="Directory to save JSON benchmark run reports (default: evaluation/results)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not persist results to SQLite database",
    )

    args = parser.parse_args()

    t0 = time.perf_counter()
    runs = run_benchmarks(
        eval_type=args.eval_type,
        dataset_path=args.dataset_path,
        top_k=args.top_k,
        retrieval_mode=args.retrieval_mode,
        output_dir=args.output_dir,
        save_to_db=not args.no_save,
    )
    total_time = time.perf_counter() - t0

    print("\n=======================================================")
    print(f"  BENCHMARK SUITE COMPLETED IN {total_time:.2f}s")
    print(f"  Total Runs Executed: {len(runs)}")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
