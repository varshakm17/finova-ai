"""Anti-Hallucination & Claim-Level Verification Evaluator for Finova AI.

Audits verification precision, recall, false acceptance rate (FAR), false rejection rate (FRR),
and failure-type detection rates (unsupported, contradicted, numeric/period mismatch, fabricated citations).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from backend.data.storage import Database
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.utils.logger import get_logger
from backend.verification.verification_models import VerificationOutcome
from backend.verification.verification_service import VerificationService
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

logger = get_logger("verification_evaluator")

DEFAULT_BENCHMARK_PATH = (
    Path(__file__).parent / "datasets" / "verification_benchmark.json"
)


class VerificationEvaluator:
    """Evaluates anti-hallucination verification engine performance and failure detection."""

    def __init__(
        self,
        verifier_service: VerificationService | None = None,
        db: Database | None = None,
    ) -> None:
        self.verifier = verifier_service or VerificationService()
        self.db = db or Database()

    def evaluate(
        self,
        dataset_path: str | Path | None = None,
        save: bool = True,
    ) -> EvaluationRun:
        """Run comprehensive claim-level verification benchmark evaluation.

        Args:
            dataset_path: Optional custom path to benchmark JSON file.
            save: Whether to persist the run to the database.

        Returns:
            EvaluationRun containing scorecards, confusion metrics, and diagnostic issues.
        """
        start_time = time.perf_counter()
        run_id = f"eval_ver_{uuid.uuid4().hex[:12]}"
        path = Path(dataset_path) if dataset_path else DEFAULT_BENCHMARK_PATH

        if not path.exists():
            raise FileNotFoundError(f"Verification benchmark not found at: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        cases: list[dict[str, Any]] = data.get("cases", [])
        total_cases = len(cases)

        case_results: list[EvaluationCaseResult] = []
        issues: list[EvaluationIssue] = []

        tp = 0
        fp = 0
        tn = 0
        fn = 0

        unsupported_total = 0
        unsupported_detected = 0
        contradicted_total = 0
        contradicted_detected = 0
        exact_verdict_matches = 0

        for case in cases:
            case_id = case["case_id"]
            claim_text = case["claim_text"]
            expected_verdict = case.get("expected_verdict", "supported")
            is_grounded_expected = bool(case.get("is_grounded", True))
            failure_type = case.get("failure_type", "none")
            raw_retrieved = case.get("retrieved_evidence", [])
            raw_calc = case.get("calculation_evidence", [])

            # Format answer text to include citation markers if provided in case
            citation_ids = case.get("citation_ids", [])
            answer_text = claim_text
            if citation_ids and not any(
                f"[{cid}]" in answer_text for cid in citation_ids
            ):
                cit_str = " " + " ".join(f"[{cid}]" for cid in citation_ids)
                base_text = claim_text.rstrip(". ")
                answer_text = f"{base_text}{cit_str}."

            # Convert evidence to typed Pydantic models
            ticker_name_map = {
                "AAPL": "Apple Inc.",
                "MSFT": "Microsoft Corporation",
                "TSLA": "Tesla, Inc.",
                "NVDA": "NVIDIA Corporation",
            }
            retrieved_ev: list[RetrievedEvidence] = []
            for item in raw_retrieved:
                ticker = item.get("company_ticker", "AAPL")
                company_title = item.get("company_name") or ticker_name_map.get(
                    ticker, ticker
                )
                retrieved_ev.append(
                    RetrievedEvidence(
                        evidence_id=item.get("evidence_id", "E1"),
                        chunk_id=item.get("chunk_id", "chunk_1"),
                        ticker=ticker,
                        company_name=company_title,
                        filing_type=item.get("filing_type", "10-K"),
                        filing_date=item.get("filing_date", "2023-11-03"),
                        report_date=item.get("reporting_period", "FY2023"),
                        accession_number=item.get(
                            "accession_number", "0000320193-23-000106"
                        ),
                        section_identifier=item.get("section_name", "ITEM_7"),
                        section_title=item.get(
                            "section_title", "Financial Disclosures"
                        ),
                        chunk_text=item.get("content", ""),
                        source_url=item.get("source_url", "https://www.sec.gov/edgar"),
                    )
                )

            calc_ev: list[CalculationEvidence] = []
            for item in raw_calc:
                calc_ev.append(
                    CalculationEvidence(
                        evidence_id=item.get(
                            "evidence_id", item.get("calculation_id", "C1")
                        ),
                        calculation_id=item.get("calculation_id", "C1"),
                        metric_name=item.get("metric_name", "gross_profit_margin"),
                        calculated_value=float(item.get("value", 0.0)),
                        unit=item.get("unit", "percentage"),
                        formula=item.get("formula", "a / b"),
                        period_end=item.get("period", "FY2023"),
                        input_observations=[],
                    )
                )

            # Execute verification
            try:
                vrun = self.verifier.verify_answer(
                    answer_id=case_id,
                    question=f"Verify assertion for {case.get('company_ticker', 'company')}",
                    answer_text=answer_text,
                    retrieved_evidence=retrieved_ev,
                    calculation_evidence=calc_ev,
                    persist=False,
                )

                if vrun.claim_results:
                    actual_outcome = vrun.claim_results[0].outcome.value
                    claim_reason = vrun.claim_results[0].verification_reason
                else:
                    actual_outcome = (
                        VerificationOutcome.SUPPORTED.value
                        if "VERIFIED" in vrun.overall_status.value
                        else VerificationOutcome.UNSUPPORTED.value
                    )
                    claim_reason = "Evaluated via overall verification status"

            except Exception as exc:
                actual_outcome = VerificationOutcome.NOT_VERIFIABLE.value
                claim_reason = f"Verification execution exception: {exc}"

            # Evaluate binary grounding (Positive = Grounded/Supported, Negative = Ungrounded/Contradicted)
            is_system_grounded = actual_outcome in {
                VerificationOutcome.SUPPORTED.value,
                VerificationOutcome.PARTIALLY_SUPPORTED.value,
            }

            if expected_verdict == "unsupported":
                unsupported_total += 1
                if actual_outcome == VerificationOutcome.UNSUPPORTED.value:
                    unsupported_detected += 1

            if expected_verdict == "contradicted":
                contradicted_total += 1
                if actual_outcome in {
                    VerificationOutcome.CONTRADICTED.value,
                    VerificationOutcome.UNSUPPORTED.value,
                }:
                    contradicted_detected += 1

            # Exact verdict match check
            verdict_matched = actual_outcome == expected_verdict
            # Partial support or unsupported count as detection for ungrounded probes
            if not is_grounded_expected and actual_outcome in {
                VerificationOutcome.UNSUPPORTED.value,
                VerificationOutcome.CONTRADICTED.value,
            }:
                grounding_correct = True
            elif is_grounded_expected and actual_outcome in {
                VerificationOutcome.SUPPORTED.value,
                VerificationOutcome.PARTIALLY_SUPPORTED.value,
            }:
                grounding_correct = True
            else:
                grounding_correct = False

            if verdict_matched:
                exact_verdict_matches += 1

            # Confusion Matrix Counts
            if is_grounded_expected and is_system_grounded:
                tp += 1
            elif not is_grounded_expected and is_system_grounded:
                fp += 1  # False Acceptance!
                issues.append(
                    EvaluationIssue(
                        run_id=run_id,
                        case_id=case_id,
                        eval_type=EvaluationType.VERIFICATION.value,
                        severity=EvaluationIssueSeverity.CRITICAL,
                        issue_type="false_acceptance",
                        description=(
                            f"CRITICAL: Case {case_id} ({failure_type}) is an ungrounded or contradicted assertion, "
                            f"but was erroneously accepted as supported."
                        ),
                        details={
                            "claim": claim_text,
                            "expected": expected_verdict,
                            "actual": actual_outcome,
                        },
                    )
                )
            elif not is_grounded_expected and not is_system_grounded:
                tn += 1
            elif is_grounded_expected and not is_system_grounded:
                fn += 1  # False Rejection
                issues.append(
                    EvaluationIssue(
                        run_id=run_id,
                        case_id=case_id,
                        eval_type=EvaluationType.VERIFICATION.value,
                        severity=EvaluationIssueSeverity.HIGH,
                        issue_type="false_rejection",
                        description=(
                            f"Case {case_id} was a grounded assertion, but was rejected or marked unsupported."
                        ),
                        details={"claim": claim_text, "reason": claim_reason},
                    )
                )

            is_case_passed = grounding_correct and (
                verdict_matched
                or (is_grounded_expected and is_system_grounded)
                or (not is_grounded_expected and not is_system_grounded)
            )

            case_results.append(
                EvaluationCaseResult(
                    run_id=run_id,
                    case_id=case_id,
                    eval_type=EvaluationType.VERIFICATION.value,
                    passed=is_case_passed,
                    expected={
                        "verdict": expected_verdict,
                        "is_grounded": is_grounded_expected,
                    },
                    actual={
                        "verdict": actual_outcome,
                        "is_grounded": is_system_grounded,
                    },
                    score=1.0 if is_case_passed else 0.0,
                    error_message=None if is_case_passed else claim_reason,
                    details={
                        "claim_text": claim_text,
                        "failure_type": failure_type,
                        "reason": claim_reason,
                        "provenance": case.get(
                            "dataset_provenance", "curated_sec_ground_truth"
                        ),
                    },
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        passed_count = sum(1 for c in case_results if c.passed)
        failed_count = total_cases - passed_count
        pass_rate = (passed_count / total_cases) if total_cases > 0 else 0.0

        # Standard Confusion Matrix Metric Calculations
        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 1.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 1.0
        f1 = (
            (2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
        far = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0
        frr = (fn / (tp + fn)) if (tp + fn) > 0 else 0.0

        unsupported_rate = (
            (unsupported_detected / unsupported_total) if unsupported_total > 0 else 1.0
        )
        contradicted_rate = (
            (contradicted_detected / contradicted_total)
            if contradicted_total > 0
            else 1.0
        )
        verdict_accuracy = (
            (exact_verdict_matches / total_cases) if total_cases > 0 else 0.0
        )

        findings = [
            f"Evaluated {total_cases} verification test cases with overall grounding accuracy {pass_rate * 100.0:.2f}%.",
            f"Claim Support Precision: {precision:.4f}, Recall: {recall:.4f}, F1: {f1:.4f}.",
            f"False Acceptance Rate (FAR): {far * 100.0:.2f}% (critical hallucination leakage).",
            f"False Rejection Rate (FRR): {frr * 100.0:.2f}%.",
            f"Unsupported claims detection rate: {unsupported_rate * 100.0:.1f}%, Contradicted detection rate: {contradicted_rate * 100.0:.1f}%.",
        ]

        summary = EvaluationSummary(
            eval_type=EvaluationType.VERIFICATION.value,
            total_cases=total_cases,
            passed_cases=passed_count,
            failed_cases=failed_count,
            pass_rate=round(pass_rate, 4),
            metrics_summary={
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1_score": round(f1, 4),
                "false_acceptance_rate": round(far, 4),
                "false_rejection_rate": round(frr, 4),
                "unsupported_detection_rate": round(unsupported_rate, 4),
                "contradicted_detection_rate": round(contradicted_rate, 4),
                "exact_verdict_accuracy": round(verdict_accuracy, 4),
                "true_positives": float(tp),
                "false_positives": float(fp),
                "true_negatives": float(tn),
                "false_negatives": float(fn),
            },
            key_findings=findings,
        )

        metrics = [
            EvaluationMetric(
                run_id=run_id,
                metric_name="precision",
                metric_value=round(precision, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={"description": "Claim support precision: TP / (TP + FP)"},
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="recall",
                metric_value=round(recall, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={"description": "Claim support recall: TP / (TP + FN)"},
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="f1_score",
                metric_value=round(f1, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={
                    "description": "Harmonic mean of precision and recall for supported claims"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="false_acceptance_rate",
                metric_value=round(far, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={
                    "description": "False Acceptance Rate (FAR): proportion of ungrounded claims incorrectly accepted"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="false_rejection_rate",
                metric_value=round(frr, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={
                    "description": "False Rejection Rate (FRR): proportion of grounded claims incorrectly rejected"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="unsupported_detection_rate",
                metric_value=round(unsupported_rate, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={
                    "description": "Proportion of ungrounded or absent claims flagged as unsupported"
                },
            ),
            EvaluationMetric(
                run_id=run_id,
                metric_name="contradicted_detection_rate",
                metric_value=round(contradicted_rate, 4),
                eval_type=EvaluationType.VERIFICATION.value,
                details={
                    "description": "Proportion of contradictory statements flagged as contradicted"
                },
            ),
        ]

        run = EvaluationRun(
            run_id=run_id,
            eval_type=EvaluationType.VERIFICATION.value,
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
                    "Failed to persist verification evaluation run to SQLite: %s", exc
                )

        logger.info(
            "Verification evaluation run=%s finished: passed=%d/%d, FAR=%.2f%%, FRR=%.2f%%, F1=%.4f",
            run_id,
            passed_count,
            total_cases,
            far * 100.0,
            frr * 100.0,
            f1,
        )
        return run
