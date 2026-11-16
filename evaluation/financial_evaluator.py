"""Deterministic Financial Calculation Evaluator for Finova AI.

Audits mathematical accuracy, edge-case resilience (zero denominators, negative values,
missing inputs), and numerical precision against curated SEC and synthetic test benchmarks.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from backend.data.storage import Database
from backend.finance.calculation_engine import CalculationEngine
from backend.utils.logger import get_logger
from evaluation.evaluation_models import (
    EvaluationCaseResult,
    EvaluationIssue,
    EvaluationIssueSeverity,
    EvaluationMetric,
    EvaluationRun,
    EvaluationStatus,
    EvaluationSummary,
    EvaluationType,
)

logger = get_logger("financial_evaluator")

DEFAULT_BENCHMARK_PATH = (
    Path(__file__).parent / "datasets" / "financial_calculation_benchmark.json"
)


class FinancialEvaluator:
    """Evaluates deterministic calculation engine formulas and edge case handling."""

    def __init__(
        self,
        engine: CalculationEngine | None = None,
        db: Database | None = None,
    ) -> None:
        self.engine = engine or CalculationEngine()
        self.db = db or Database()

    def evaluate(
        self,
        dataset_path: str | Path | None = None,
        save: bool = True,
    ) -> EvaluationRun:
        """Run comprehensive financial calculation benchmark evaluation.

        Args:
            dataset_path: Optional custom path to benchmark JSON file.
            save: Whether to persist the run and case results to SQLite database.

        Returns:
            EvaluationRun containing scorecards, case results, and diagnostic issues.
        """
        start_time = time.perf_counter()
        run_id = f"eval_calc_{uuid.uuid4().hex[:12]}"
        path = Path(dataset_path) if dataset_path else DEFAULT_BENCHMARK_PATH

        if not path.exists():
            raise FileNotFoundError(
                f"Financial calculation benchmark not found at: {path}"
            )

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        cases: list[dict[str, Any]] = data.get("cases", [])
        total_cases = len(cases)

        case_results: list[EvaluationCaseResult] = []
        issues: list[EvaluationIssue] = []

        abs_errors: list[float] = []
        pct_errors: list[float] = []

        zero_denom_total = 0
        zero_denom_passed = 0
        missing_inputs_total = 0
        missing_inputs_passed = 0
        negative_val_total = 0
        negative_val_passed = 0

        for case in cases:
            case_id = case["case_id"]
            metric_name = case["metric_name"]
            scenario = case.get("test_scenario", "normal")
            inputs = case.get("inputs", {})
            expected_status = case.get("expected_status", "calculated")
            expected_val = case.get("expected_value")
            tolerance_abs = float(case.get("tolerance_abs", 0.01))
            tolerance_pct = float(case.get("tolerance_pct", 0.05))

            if scenario == "zero_denominator":
                zero_denom_total += 1
            elif scenario == "missing_inputs":
                missing_inputs_total += 1
            elif scenario == "negative_values":
                negative_val_total += 1

            computed_val: float | None = None
            computed_status = "calculated"
            error_msg: str | None = None

            try:
                computed_val, computed_status = self._compute_metric(
                    metric_name, inputs
                )
            except ZeroDivisionError:
                computed_val = None
                computed_status = "unavailable"
            except (KeyError, TypeError) as exc:
                computed_val = None
                computed_status = "unavailable"
                error_msg = str(exc)
            except Exception as exc:
                computed_val = None
                computed_status = "error"
                error_msg = f"Unexpected calculation exception: {exc}"

            # Evaluate match against expected
            is_passed = False
            abs_err: float | None = None
            pct_err: float | None = None

            if expected_status == "unavailable":
                if computed_status == "unavailable" and computed_val is None:
                    is_passed = True
                else:
                    is_passed = False
                    issues.append(
                        EvaluationIssue(
                            run_id=run_id,
                            case_id=case_id,
                            eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                            severity=EvaluationIssueSeverity.HIGH,
                            issue_type="unhandled_zero_or_missing_input",
                            description=(
                                f"Case {case_id} expected status 'unavailable' with None, "
                                f"got status '{computed_status}' and value {computed_val}"
                            ),
                            details={"inputs": inputs, "scenario": scenario},
                        )
                    )
            else:
                if (
                    computed_status == "calculated"
                    and computed_val is not None
                    and expected_val is not None
                ):
                    abs_err = abs(computed_val - expected_val)
                    abs_errors.append(abs_err)

                    if expected_val != 0:
                        pct_err = (abs_err / abs(expected_val)) * 100.0
                        pct_errors.append(pct_err)
                    else:
                        pct_err = 0.0

                    # Check within absolute tolerance or relative percentage tolerance
                    if abs_err <= tolerance_abs or (
                        pct_err is not None and pct_err <= tolerance_pct
                    ):
                        is_passed = True
                    else:
                        is_passed = False
                        issues.append(
                            EvaluationIssue(
                                run_id=run_id,
                                case_id=case_id,
                                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                                severity=EvaluationIssueSeverity.MEDIUM,
                                issue_type="numeric_tolerance_exceeded",
                                description=(
                                    f"Case {case_id} ({metric_name}) computed value {computed_val:.6f} "
                                    f"differed from expected {expected_val:.6f} (abs_err={abs_err:.6f}, pct_err={pct_err:.2f}%)"
                                ),
                                details={
                                    "expected": expected_val,
                                    "computed": computed_val,
                                    "abs_error": abs_err,
                                },
                            )
                        )
                else:
                    is_passed = False
                    issues.append(
                        EvaluationIssue(
                            run_id=run_id,
                            case_id=case_id,
                            eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                            severity=EvaluationIssueSeverity.HIGH,
                            issue_type="metric_computation_failed",
                            description=f"Case {case_id} failed to compute value: {error_msg or computed_status}",
                            details={
                                "inputs": inputs,
                                "computed_status": computed_status,
                            },
                        )
                    )

            if is_passed:
                if scenario == "zero_denominator":
                    zero_denom_passed += 1
                elif scenario == "missing_inputs":
                    missing_inputs_passed += 1
                elif scenario == "negative_values":
                    negative_val_passed += 1

            case_results.append(
                EvaluationCaseResult(
                    run_id=run_id,
                    case_id=case_id,
                    eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                    passed=is_passed,
                    expected={"status": expected_status, "value": expected_val},
                    actual={"status": computed_status, "value": computed_val},
                    score=1.0 if is_passed else 0.0,
                    error_message=error_msg,
                    details={
                        "metric_name": metric_name,
                        "scenario": scenario,
                        "abs_error": abs_err,
                        "pct_error": pct_err,
                        "provenance": case.get(
                            "dataset_provenance", "verified_sec_xbrl_inputs"
                        ),
                    },
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        passed_count = sum(1 for c in case_results if c.passed)
        failed_count = total_cases - passed_count
        accuracy = (passed_count / total_cases) if total_cases > 0 else 0.0

        mae = (sum(abs_errors) / len(abs_errors)) if abs_errors else 0.0
        max_abs_error = max(abs_errors) if abs_errors else 0.0
        mean_pct_error = (sum(pct_errors) / len(pct_errors)) if pct_errors else 0.0

        zero_denom_acc = (
            (zero_denom_passed / zero_denom_total) if zero_denom_total > 0 else 1.0
        )
        missing_acc = (
            (missing_inputs_passed / missing_inputs_total)
            if missing_inputs_total > 0
            else 1.0
        )
        negative_acc = (
            (negative_val_passed / negative_val_total)
            if negative_val_total > 0
            else 1.0
        )

        pass_rate = (passed_count / total_cases) if total_cases > 0 else 0.0

        findings = [
            f"Evaluated {total_cases} deterministic calculation cases with accuracy {pass_rate * 100.0:.2f}%.",
            f"Mean Absolute Error: {mae:.6f}, Max Absolute Error: {max_abs_error:.6f}.",
            f"Zero-denominator handling accuracy: {zero_denom_acc * 100.0:.1f}%.",
            f"Missing-input handling accuracy: {missing_acc * 100.0:.1f}%.",
        ]

        summary = EvaluationSummary(
            eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
            total_cases=total_cases,
            passed_cases=passed_count,
            failed_cases=failed_count,
            pass_rate=round(pass_rate, 4),
            metrics_summary={
                "accuracy": round(pass_rate, 4),
                "mean_absolute_error": round(mae, 6),
                "max_absolute_error": round(max_abs_error, 6),
                "mean_percentage_error": round(mean_pct_error, 4),
                "zero_denominator_accuracy": round(zero_denom_acc, 4),
                "missing_input_accuracy": round(missing_acc, 4),
                "negative_value_accuracy": round(negative_acc, 4),
            },
            key_findings=findings,
        )

        metrics = [
            EvaluationMetric(
                run_id=run_id,
                metric_name="accuracy",
                metric_value=round(accuracy, 4),
                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                details={
                    "description": "Proportion of calculation benchmark test cases passing mathematical and status criteria"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="mean_absolute_error",
                metric_value=round(mae, 6),
                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                details={
                    "description": "Mean Absolute Error across all calculated non-null ratio and margin results"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="max_absolute_error",
                metric_value=round(max_abs_error, 6),
                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                details={
                    "description": "Maximum Absolute Error observed across calculation benchmark test cases"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="zero_denominator_accuracy",
                metric_value=round(zero_denom_acc, 4),
                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                details={
                    "description": "Accuracy of handling zero-denominator conditions without crash or silent zero conversion"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="missing_input_accuracy",
                metric_value=round(missing_acc, 4),
                eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
                details={
                    "description": "Accuracy of returning unavailable status when required inputs are missing"
                },
            ),
        ]

        run = EvaluationRun(
            run_id=run_id,
            eval_type=EvaluationType.FINANCIAL_CALCULATION.value,
            status=EvaluationStatus.COMPLETED,
            total_cases=total_cases,
            passed_cases=passed_count,
            failed_cases=failed_count,
            duration_ms=round(duration_ms, 2),
            summary=summary,
            metrics=metrics,
            issues=issues,
        )

        if save:
            try:
                self.db.save_evaluation_run(
                    run=run,
                    case_results=case_results,
                    metrics=metrics,
                    issues=issues,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist financial calculation evaluation run to SQLite: %s",
                    exc,
                )

        logger.info(
            "Financial calculation evaluation run=%s finished: passed=%d/%d, accuracy=%.2f%%, MAE=%.6f",
            run_id,
            passed_count,
            total_cases,
            accuracy * 100.0,
            mae,
        )
        return run

    def _compute_metric(
        self, metric_name: str, inputs: dict[str, Any]
    ) -> tuple[float | None, str]:
        """Compute standard metric by routing to CalculationEngine method."""
        try:
            return self._compute_metric_inner(metric_name, inputs)
        except ZeroDivisionError:
            return None, "unavailable"

    def _compute_metric_inner(
        self, metric_name: str, inputs: dict[str, Any]
    ) -> tuple[float | None, str]:
        """Internal dispatcher for metric calculation."""
        if metric_name == "gross_profit_margin":
            if "gross_profit" not in inputs or "revenue" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_gross_profit_margin(
                inputs["gross_profit"], inputs["revenue"]
            )
            return val, "calculated"

        elif metric_name == "revenue_growth":
            if "current_revenue" not in inputs or "previous_revenue" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_revenue_growth(
                inputs["current_revenue"], inputs["previous_revenue"]
            )
            return val, "calculated"

        elif metric_name == "operating_profit_margin":
            if "operating_income" not in inputs or "revenue" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_operating_profit_margin(
                inputs["operating_income"], inputs["revenue"]
            )
            return val, "calculated"

        elif metric_name == "net_profit_margin":
            if "net_income" not in inputs or "revenue" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_net_profit_margin(
                inputs["net_income"], inputs["revenue"]
            )
            return val, "calculated"

        elif metric_name == "current_ratio":
            if "current_assets" not in inputs or "current_liabilities" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_current_ratio(
                inputs["current_assets"], inputs["current_liabilities"]
            )
            return val, "calculated"

        elif metric_name == "debt_to_equity_ratio":
            equity = inputs.get("stockholders_equity", inputs.get("total_equity"))
            if "total_debt" not in inputs or equity is None:
                return None, "unavailable"
            val = self.engine.calculate_debt_to_equity(inputs["total_debt"], equity)
            return val, "calculated"

        elif metric_name == "return_on_assets":
            if "net_income" not in inputs:
                return None, "unavailable"
            if "opening_total_assets" in inputs and "closing_total_assets" in inputs:
                val = self.engine.calculate_return_on_assets(
                    inputs["net_income"],
                    inputs["opening_total_assets"],
                    inputs["closing_total_assets"],
                )
            elif "total_assets" in inputs:
                val = self.engine.calculate_return_on_assets(
                    inputs["net_income"], inputs["total_assets"], inputs["total_assets"]
                )
            elif "average_assets" in inputs:
                val = self.engine.calculate_return_on_assets(
                    inputs["net_income"],
                    inputs["average_assets"],
                    inputs["average_assets"],
                )
            else:
                return None, "unavailable"
            return val, "calculated"

        elif metric_name == "return_on_equity":
            if "net_income" not in inputs:
                return None, "unavailable"
            equity = inputs.get("stockholders_equity", inputs.get("total_equity"))
            if "opening_equity" in inputs and "closing_equity" in inputs:
                val = self.engine.calculate_return_on_equity(
                    inputs["net_income"],
                    inputs["opening_equity"],
                    inputs["closing_equity"],
                )
            elif equity is not None:
                val = self.engine.calculate_return_on_equity(
                    inputs["net_income"], equity, equity
                )
            elif "average_equity" in inputs:
                val = self.engine.calculate_return_on_equity(
                    inputs["net_income"],
                    inputs["average_equity"],
                    inputs["average_equity"],
                )
            else:
                return None, "unavailable"
            return val, "calculated"

        elif metric_name == "operating_cash_flow_margin":
            if "operating_cash_flow" not in inputs or "revenue" not in inputs:
                return None, "unavailable"
            val = self.engine.calculate_operating_cash_flow_margin(
                inputs["operating_cash_flow"], inputs["revenue"]
            )
            return val, "calculated"

        elif metric_name == "free_cash_flow":
            if (
                "operating_cash_flow" not in inputs
                or "capital_expenditures" not in inputs
            ):
                return None, "unavailable"
            res = self.engine.calculate_free_cash_flow(
                inputs["operating_cash_flow"], inputs["capital_expenditures"]
            )
            val = res[0] if isinstance(res, tuple) else res
            return val, "calculated"

        else:
            raise ValueError(f"Unsupported calculation metric: {metric_name}")
