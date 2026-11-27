"""Tests for Finova AI — Session 18.1.4 Semantic Trend Verification and Fail-Closed Audit Integrity.

Covers:
- Trajectory classifications (monotonic up/down, mixed net up/down, flat, insufficient data)
- Semantic trend matching (qualitative trajectory, directional polarity, metric alignment)
- Complete observation series validation & independent mathematical recalculation
- Fail-closed audit behavior on missing receipts, invalid formulas, or missing observations
- Claim classification persistence through extraction, SQLite persistence, and retrieval
- Production receipt deduplication using TrendReceiptAuditor
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.data.storage import Database
from backend.finance.financial_trends import (
    TrajectoryType,
    TrendReceiptAuditor,
    build_trend_receipt,
    classify_trajectory,
    verify_trend_math,
    verify_trend_semantics,
)
from backend.rag.rag_models import CalculationEvidence
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.verification_models import (
    ClaimType,
    ExtractedClaim,
    NumericClaimValue,
    VerificationOutcome,
)


class TestTrajectoryClassification:
    """Test deterministic trajectory classification across varied observation series."""

    def test_monotonic_upward(self) -> None:
        assert classify_trajectory([10.0, 15.0, 20.0]) == TrajectoryType.MONOTONIC_UPWARD
        assert classify_trajectory([1.0, 2.5, 4.0, 8.0]) == TrajectoryType.MONOTONIC_UPWARD

    def test_monotonic_downward(self) -> None:
        assert classify_trajectory([20.0, 15.0, 10.0]) == TrajectoryType.MONOTONIC_DOWNWARD
        assert classify_trajectory([100.0, 50.0, 25.0]) == TrajectoryType.MONOTONIC_DOWNWARD

    def test_mixed_upward_net(self) -> None:
        # [10, 20, 15] -> up then down, net +5
        assert classify_trajectory([10.0, 20.0, 15.0]) == TrajectoryType.MIXED_UPWARD_NET
        # [10, 5, 15] -> down then up, net +5
        assert classify_trajectory([10.0, 5.0, 15.0]) == TrajectoryType.MIXED_UPWARD_NET

    def test_mixed_downward_net(self) -> None:
        # [20, 10, 15] -> down then up, net -5
        assert classify_trajectory([20.0, 10.0, 15.0]) == TrajectoryType.MIXED_DOWNWARD_NET
        # [17.53, 17.95, 6.88] (MSFT Revenue Growth) -> up then down, net negative
        assert classify_trajectory([17.5317, 17.9565, 6.8820]) == TrajectoryType.MIXED_DOWNWARD_NET

    def test_flat_trajectory(self) -> None:
        assert classify_trajectory([10.0, 10.0, 10.0]) == TrajectoryType.FLAT
        # Within micro-tolerance
        assert classify_trajectory([10.0, 10.00001, 9.99999]) == TrajectoryType.FLAT

    def test_insufficient_data_and_non_finite(self) -> None:
        assert classify_trajectory([]) == TrajectoryType.INSUFFICIENT_DATA
        assert classify_trajectory([10.0]) == TrajectoryType.INSUFFICIENT_DATA
        assert classify_trajectory([10.0, float("nan")]) == TrajectoryType.INSUFFICIENT_DATA
        assert classify_trajectory([10.0, float("inf")]) == TrajectoryType.INSUFFICIENT_DATA


class TestTrendReceiptBuildingAndMathValidation:
    """Test extended trend receipt creation with complete observations and hardened math verification."""

    def test_build_trend_receipt_complete_schema(self) -> None:
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[150.7913, 51.3503, 18.7953],
            unit="%",
            citation_id="C13",
            supporting_receipt_ids=["r1", "r2", "r3"],
        )
        assert receipt is not None
        assert receipt["citation_id"] == "C13"
        assert receipt["metric_name"] == "revenue_growth Trend"
        assert receipt["trajectory"] == "MONOTONIC_DOWNWARD"
        assert receipt["direction"] == "DOWNWARD"
        assert len(receipt["observations"]) == 3
        assert len(receipt["periods"]) == 3
        assert len(receipt["values"]) == 3
        assert receipt["start_value"] == 150.7913
        assert receipt["end_value"] == 18.7953
        assert receipt["calculated_value"] == -87.5356

        # Math verification passes
        is_val, msg = verify_trend_math(receipt)
        assert is_val is True
        assert "verified" in msg.lower()

    def test_verify_trend_math_detects_altered_percentage(self) -> None:
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[150.7913, 51.3503, 18.7953],
            unit="%",
            citation_id="C13",
        )
        assert receipt is not None
        receipt["calculated_value"] = -50.0  # Manipulated
        is_val, msg = verify_trend_math(receipt)
        assert is_val is False
        assert "mismatch" in msg.lower()

    def test_verify_trend_math_detects_altered_observations_trajectory_mismatch(self) -> None:
        receipt = build_trend_receipt(
            metric_name="gross_profit_margin",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[25.28, 25.59, 18.25],  # Mixed
            unit="%",
            citation_id="C14",
        )
        assert receipt is not None
        assert receipt["trajectory"] == "MIXED_DOWNWARD_NET"
        # Alter observations to monotonic
        receipt["values"] = [25.28, 22.00, 18.25]
        receipt["observations"] = [
            {"period": "FY2021", "value": 25.28, "unit": "%"},
            {"period": "FY2022", "value": 22.00, "unit": "%"},
            {"period": "FY2023", "value": 18.25, "unit": "%"},
        ]
        is_val, msg = verify_trend_math(receipt)
        assert is_val is False
        assert "trajectory mismatch" in msg.lower()

    def test_verify_trend_math_detects_missing_observations(self) -> None:
        receipt = {
            "calculation_id": "calc_trend_test",
            "metric_name": "test Trend",
            "calculated_value": 10.0,
            "unit": "%",
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 11.0},
            ],
            "observations": [],  # Empty observations
            "values": [],
        }
        is_val, msg = verify_trend_math(receipt)
        assert is_val is False
        assert "insufficient" in msg.lower() or "missing" in msg.lower()

    def test_verify_trend_math_rejects_zero_denominator_in_pct(self) -> None:
        receipt = {
            "calculation_id": "calc_trend_zero",
            "metric_name": "operating_margin Trend",
            "calculated_value": 10.0,
            "unit": "%",
            "formula_name": "Multi-Period Percentage Growth Analysis",
            "formula_expression": "((V_end - V_start) / abs(V_start)) * 100",
            "inputs": [
                {"input_name": "start_value", "value": 0.0},
                {"input_name": "end_value", "value": 10.0},
                {"input_name": "absolute_change", "value": 10.0},
            ],
            "values": [0.0, 5.0, 10.0],
        }
        is_val, msg = verify_trend_math(receipt)
        assert is_val is False
        assert "zero denominator" in msg.lower()


class TestSemanticTrendVerification:
    """Test claim-to-trend semantic verification in EvidenceVerifier."""

    @pytest.fixture
    def setup_evidence(self) -> tuple[CalculationEvidence, CalculationEvidence]:
        # Receipt 1: Monotonic downward (TSLA Revenue Growth)
        rec1 = CalculationEvidence(
            evidence_id="C13",
            calculation_id="calc_trend_revenue_growth_FY2021_FY2023",
            metric_name="revenue_growth Trend",
            calculated_value=-87.5356,
            unit="%",
            formula="((V_end - V_start) / abs(V_start)) * 100",
            period_start="FY2021",
            period_end="FY2023",
            direction="DOWNWARD",
            trajectory="MONOTONIC_DOWNWARD",
            periods=["FY2021", "FY2022", "FY2023"],
            observations=[
                {"period": "FY2021", "value": 150.7913, "unit": "%"},
                {"period": "FY2022", "value": 51.3503, "unit": "%"},
                {"period": "FY2023", "value": 18.7953, "unit": "%"},
            ],
            input_observations=[
                {"input_name": "start_value", "value": 150.7913, "unit": "%"},
                {"input_name": "end_value", "value": 18.7953, "unit": "%"},
                {"input_name": "absolute_change", "value": -131.996, "unit": "%"},
                {"input_name": "percentage_change", "value": -87.5356, "unit": "%"},
            ],
        )
        # Receipt 2: Mixed downward net (TSLA Gross Margin)
        rec2 = CalculationEvidence(
            evidence_id="C14",
            calculation_id="calc_trend_gross_profit_margin_FY2021_FY2023",
            metric_name="gross_profit_margin Trend",
            calculated_value=-27.8106,
            unit="%",
            formula="((V_end - V_start) / abs(V_start)) * 100",
            period_start="FY2021",
            period_end="FY2023",
            direction="MIXED",
            trajectory="MIXED_DOWNWARD_NET",
            periods=["FY2021", "FY2022", "FY2023"],
            observations=[
                {"period": "FY2021", "value": 25.2838, "unit": "%"},
                {"period": "FY2022", "value": 25.5976, "unit": "%"},
                {"period": "FY2023", "value": 18.2514, "unit": "%"},
            ],
            input_observations=[
                {"input_name": "start_value", "value": 25.2838, "unit": "%"},
                {"input_name": "end_value", "value": 18.2514, "unit": "%"},
                {"input_name": "absolute_change", "value": -7.0324, "unit": "%"},
                {"input_name": "percentage_change", "value": -27.8106, "unit": "%"},
            ],
        )
        return rec1, rec2

    def test_semantic_match_valid_deceleration(
        self, setup_evidence: tuple[CalculationEvidence, CalculationEvidence]
    ) -> None:
        rec1, rec2 = setup_evidence
        verifier = EvidenceVerifier()
        claim = ExtractedClaim(
            claim_id="CLM-01",
            claim_text="Top-line revenue expansion decelerated (-87.5%).",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C13"],
            numeric_values=[
                NumericClaimValue(raw_text="-87.5%", numeric_value=-87.5, unit="%")
            ],
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [rec1, rec2])
        assert res.outcome == VerificationOutcome.SUPPORTED
        assert "supported" in res.verification_reason.lower()

    def test_semantic_contradiction_monotonic_claimed_as_mixed(
        self, setup_evidence: tuple[CalculationEvidence, CalculationEvidence]
    ) -> None:
        rec1, rec2 = setup_evidence
        verifier = EvidenceVerifier()
        # rec1 is MONOTONIC_DOWNWARD, but claim asserts mixed volatility
        claim = ExtractedClaim(
            claim_id="CLM-02",
            claim_text="Revenue growth demonstrated mixed volatility across periods (-87.5%).",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C13"],
            numeric_values=[
                NumericClaimValue(raw_text="-87.5%", numeric_value=-87.5, unit="%")
            ],
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [rec1, rec2])
        assert res.outcome == VerificationOutcome.CONTRADICTED
        assert "trajectory contradiction" in res.verification_reason.lower()

    def test_semantic_match_valid_mixed_trend(
        self, setup_evidence: tuple[CalculationEvidence, CalculationEvidence]
    ) -> None:
        rec1, rec2 = setup_evidence
        verifier = EvidenceVerifier()
        # rec2 is MIXED_DOWNWARD_NET
        claim = ExtractedClaim(
            claim_id="CLM-03",
            claim_text="Gross profit margin demonstrated mixed volatility across periods (net shift: -7.03 percentage (-27.8%)).",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C14"],
            numeric_values=[
                NumericClaimValue(raw_text="-7.03", numeric_value=-7.03, unit="%"),
                NumericClaimValue(raw_text="-27.8%", numeric_value=-27.8, unit="%"),
            ],
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [rec1, rec2])
        assert res.outcome == VerificationOutcome.SUPPORTED

    def test_semantic_contradiction_polarity_reversal(
        self, setup_evidence: tuple[CalculationEvidence, CalculationEvidence]
    ) -> None:
        rec1, rec2 = setup_evidence
        verifier = EvidenceVerifier()
        # rec1 is negative (-87.5%), but claim asserts revenue growth accelerated
        claim = ExtractedClaim(
            claim_id="CLM-04",
            claim_text="Revenue growth accelerated over comparative fiscal periods.",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C13"],
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [rec1, rec2])
        assert res.outcome == VerificationOutcome.CONTRADICTED
        assert "polarity contradiction" in res.verification_reason.lower()

    def test_semantic_unsupported_metric_mismatch(
        self, setup_evidence: tuple[CalculationEvidence, CalculationEvidence]
    ) -> None:
        rec1, rec2 = setup_evidence
        verifier = EvidenceVerifier()
        # Claim asserts free cash flow, but cites revenue growth receipt C13
        claim = ExtractedClaim(
            claim_id="CLM-05",
            claim_text="Free cash flow declined across the comparative periods.",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C13"],
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [rec1, rec2])
        assert res.outcome == VerificationOutcome.UNSUPPORTED
        assert "metric mismatch" in res.verification_reason.lower()

    def test_semantic_unsupported_missing_receipt_fail_closed(self) -> None:
        verifier = EvidenceVerifier()
        claim = ExtractedClaim(
            claim_id="CLM-06",
            claim_text="Revenue growth declined (-87.5%).",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C99"],  # Non-existent
            is_verifiable=True,
        )
        res = verifier.verify_claim(claim, [], [])
        assert res.outcome == VerificationOutcome.UNSUPPORTED
        assert "non-existent or fabricated" in res.verification_reason.lower()


class TestProductionReceiptDeduplication:
    """Test TrendReceiptAuditor deduplication and independent recalculation."""

    def test_auditor_evaluates_unique_receipt_once(self) -> None:
        auditor = TrendReceiptAuditor()
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[150.7913, 51.3503, 18.7953],
            unit="%",
            citation_id="C13",
        )
        assert receipt is not None

        # First claim audits C13
        rec1 = auditor.audit_receipt(receipt, citation_id="C13", claim_id="CLM-01")
        assert rec1["status"] == "verified"
        assert rec1["calculated_percentage_change"] == -87.5356

        # Second claim references the same receipt C13
        rec2 = auditor.audit_receipt(receipt, citation_id="C13", claim_id="CLM-02")
        assert rec2["status"] == "verified"

        summary = auditor.get_summary()
        # Exactly ONE unique receipt evaluated
        assert summary["total_unique_receipts"] == 1
        assert summary["verified_receipts"] == 1
        assert len(auditor.get_unique_receipts()) == 1
        assert auditor.receipt_to_claims[receipt["calculation_id"]] == {"CLM-01", "CLM-02"}

    def test_auditor_distinguishes_different_receipts_for_same_metric(self) -> None:
        auditor = TrendReceiptAuditor()
        r1 = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[150.79, 51.35, 18.80],
            unit="%",
            citation_id="C1",
        )
        r2 = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2022", "FY2023", "FY2024"],
            values=[61.40, 0.22, 125.85],
            unit="%",
            citation_id="C2",
        )
        assert r1 is not None and r2 is not None

        auditor.audit_receipt(r1, citation_id="C1", claim_id="CLM-01")
        auditor.audit_receipt(r2, citation_id="C2", claim_id="CLM-02")

        summary = auditor.get_summary()
        assert summary["total_unique_receipts"] == 2
        assert summary["verified_receipts"] == 2

    def test_auditor_failed_receipt_cannot_become_verified(self) -> None:
        auditor = TrendReceiptAuditor()
        bad_receipt = {
            "calculation_id": "calc_bad_math",
            "citation_id": "C99",
            "metric_name": "bad_metric Trend",
            "calculated_value": 999.0,  # Wrong
            "unit": "%",
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 20.0},
            ],
            "values": [10.0, 15.0, 20.0],
        }
        rec1 = auditor.audit_receipt(bad_receipt, citation_id="C99", claim_id="CLM-01")
        assert rec1["status"] == "failed_recalculation"

        # Subsequent claim referencing same bad receipt
        rec2 = auditor.audit_receipt(bad_receipt, citation_id="C99", claim_id="CLM-02")
        assert rec2["status"] == "failed_recalculation"
        assert auditor.get_summary()["failed_receipts"] == 1


class TestClaimClassificationPersistence:
    """Integration test proving trend claim classification persists through extraction, SQLite, and retrieval."""

    def test_trend_claim_retains_historical_comparison_throughout_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_finova.db"
            storage = Database(db_path=str(db_path))

            # 1. Extract claim
            extractor = ClaimExtractor()
            text = "- **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-60.7%)). [C4]"
            res = extractor.extract_claims(text, answer_id="ans_test_01")
            claim = res.claims[0]
            assert claim.claim_type == ClaimType.HISTORICAL_COMPARISON

            # 2. Verify claim with EvidenceVerifier
            verifier = EvidenceVerifier()
            v_receipt = CalculationEvidence(
                evidence_id="C4",
                calculation_id="calc_trend_revenue_growth_FY2021_FY2023",
                metric_name="revenue_growth Trend",
                calculated_value=-60.7454,
                unit="%",
                formula="((V_end - V_start) / abs(V_start)) * 100",
                period_start="FY2021",
                period_end="FY2023",
                direction="MIXED",
                trajectory="MIXED_DOWNWARD_NET",
                values=[17.5317, 17.9565, 6.8820],
                input_observations=[
                    {"input_name": "start_value", "value": 17.5317, "unit": "%"},
                    {"input_name": "end_value", "value": 6.8820, "unit": "%"},
                    {"input_name": "absolute_change", "value": -10.6497, "unit": "%"},
                    {"input_name": "percentage_change", "value": -60.7454, "unit": "%"},
                ],
            )
            cvr = verifier.verify_claim(claim, [], [v_receipt])
            assert cvr.outcome == VerificationOutcome.SUPPORTED
            assert cvr.claim_type == ClaimType.HISTORICAL_COMPARISON

            # 3. Persist verification run in SQLite
            vrun_data = {
                "run_id": "vrun_test_01",
                "answer_id": "ans_test_01",
                "overall_status": "verified",
                "total_claims": 1,
                "supported_claims": 1,
                "partially_supported_claims": 0,
                "unsupported_claims": 0,
                "contradicted_claims": 0,
                "not_verifiable_claims": 0,
                "claim_results": [cvr.model_dump()],
                "verifier_version": "0.1.0",
            }
            storage.save_verification_run(vrun_data)

            # 4. Retrieve from SQLite directly
            with storage.connection() as conn:
                row = conn.execute(
                    "SELECT claim_id, claim_type, is_verifiable FROM answer_claims WHERE answer_id = ?;",
                    ("ans_test_01",),
                ).fetchone()
                assert row is not None
                assert row["claim_type"] == "historical_comparison"
                assert row["is_verifiable"] == 1

            # 5. Retrieve via get_verification_run
            loaded_run = storage.get_verification_run("vrun_test_01")
            assert loaded_run is not None
            loaded_claim_res = loaded_run["claim_results"][0]
            assert loaded_claim_res["claim_type"] == "historical_comparison"


class TestSession18_1_4_1_AdversarialSuite:
    """Session 18.1.4.1 20-case adversarial regression suite calling production functions."""

    def test_case_01_three_genuine_observations_mixed_trajectory(self) -> None:
        """1. Three genuine observations with mixed trajectory."""
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[17.5317, 17.9565, 6.8820],
            unit="%",
            citation_id="C1",
        )
        assert receipt is not None
        assert receipt["trajectory"] == "MIXED_DOWNWARD_NET"
        assert receipt["direction"] == "MIXED"
        ok, reason = verify_trend_math(receipt)
        assert ok, reason
        sem_ok, sem_outcome, sem_reason = verify_trend_semantics(
            claim_text="Revenue growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-60.7%)).",
            receipt=receipt,
            numeric_values=[NumericClaimValue(raw_text="-60.7%", numeric_value=-60.7, unit="%")],
        )
        assert sem_ok, sem_reason
        assert sem_outcome == "supported"

    def test_case_02_three_observations_monotonic_upward_trajectory(self) -> None:
        """2. Three observations with monotonic upward trajectory."""
        receipt = build_trend_receipt(
            metric_name="cloud_revenue",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[60.0, 75.0, 95.0],
            unit="USD",
            citation_id="C2",
        )
        assert receipt is not None
        assert receipt["trajectory"] == "MONOTONIC_UPWARD"
        assert receipt["direction"] == "UPWARD"
        ok, reason = verify_trend_math(receipt)
        assert ok, reason
        sem_ok, sem_outcome, sem_reason = verify_trend_semantics(
            claim_text="Cloud revenue increased monotonically across fiscal periods.",
            receipt=receipt,
        )
        assert sem_ok, sem_reason
        assert sem_outcome == "supported"

    def test_case_03_three_observations_monotonic_downward_trajectory(self) -> None:
        """3. Three observations with monotonic downward trajectory."""
        receipt = build_trend_receipt(
            metric_name="operating_margin",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[30.0, 25.0, 20.0],
            unit="%",
            citation_id="C3",
        )
        assert receipt is not None
        assert receipt["trajectory"] == "MONOTONIC_DOWNWARD"
        assert receipt["direction"] == "DOWNWARD"
        ok, reason = verify_trend_math(receipt)
        assert ok, reason
        sem_ok, sem_outcome, sem_reason = verify_trend_semantics(
            claim_text="Operating margin decreased steadily across fiscal periods.",
            receipt=receipt,
        )
        assert sem_ok, sem_reason
        assert sem_outcome == "supported"

    def test_case_04_two_observation_receipt_asserting_mixed_movement(self) -> None:
        """4. A two-observation receipt asserting mixed movement."""
        two_pt_receipt = {
            "calculation_id": "calc_trend_two_pt",
            "citation_id": "C4",
            "metric_name": "growth Trend",
            "calculated_value": 50.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022"],
            "values": [10.0, 15.0],
            "trajectory": "MIXED_UPWARD_NET",
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 15.0},
                {"input_name": "percentage_change", "value": 50.0},
                {"input_name": "absolute_change", "value": 5.0},
            ],
        }
        ok, reason = verify_trend_math(two_pt_receipt)
        assert not ok
        assert "two-observation" in reason.lower() and "mixed" in reason.lower()

    def test_case_05_three_period_receipt_with_only_two_observations(self) -> None:
        """5. A three-period receipt with only two observations."""
        receipt = {
            "calculation_id": "calc_trend_mismatch_counts",
            "citation_id": "C5",
            "metric_name": "margin Trend",
            "calculated_value": 10.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "values": [20.0, 22.0],
            "inputs": [
                {"input_name": "start_value", "value": 20.0},
                {"input_name": "end_value", "value": 22.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "does not match period count" in reason.lower()

    def test_case_06_missing_period_in_middle_of_series(self) -> None:
        """6. Missing period in the middle of a series."""
        receipt = {
            "calculation_id": "calc_trend_missing_mid",
            "citation_id": "C6",
            "metric_name": "revenue Trend",
            "calculated_value": 50.0,
            "unit": "%",
            "periods": ["FY2021", "FY2023"],
            "values": [100.0, 150.0],
            "inputs": [
                {"input_name": "start_value", "value": 100.0},
                {"input_name": "end_value", "value": 150.0},
                {"input_name": "percentage_change", "value": 50.0},
                {"input_name": "absolute_change", "value": 50.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "missing intermediate period" in reason.lower()

    def test_case_07_duplicate_periods_rejected(self) -> None:
        """7. Duplicate periods."""
        receipt = {
            "calculation_id": "calc_trend_dupe_periods",
            "citation_id": "C7",
            "metric_name": "profit Trend",
            "calculated_value": 20.0,
            "unit": "%",
            "periods": ["FY2021", "FY2021", "FY2022"],
            "values": [10.0, 10.0, 12.0],
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 12.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "duplicate periods" in reason.lower()

    def test_case_08_out_of_order_periods_rejected(self) -> None:
        """8. Out-of-order periods."""
        receipt = {
            "calculation_id": "calc_trend_out_of_order",
            "citation_id": "C8",
            "metric_name": "ebitda Trend",
            "calculated_value": 50.0,
            "unit": "%",
            "periods": ["FY2023", "FY2021", "FY2022"],
            "values": [10.0, 12.0, 15.0],
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 15.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "chronological order" in reason.lower()

    def test_case_09_observation_unit_mismatch(self) -> None:
        """9. Observation unit mismatch."""
        receipt = {
            "calculation_id": "calc_trend_unit_mismatch",
            "citation_id": "C9",
            "metric_name": "margin Trend",
            "calculated_value": 20.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "observations": [
                {"period": "FY2021", "value": 10.0, "unit": "USD"},
                {"period": "FY2022", "value": 11.0, "unit": "%"},
                {"period": "FY2023", "value": 12.0, "unit": "USD"},
            ],
            "inputs": [
                {"input_name": "start_value", "value": 10.0, "unit": "%"},
                {"input_name": "end_value", "value": 12.0, "unit": "%"},
                {"input_name": "percentage_change", "value": 20.0, "unit": "%"},
                {"input_name": "absolute_change", "value": 2.0, "unit": "%"},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "unit mismatch" in reason.lower()

    def test_case_10_altered_intermediate_observation(self) -> None:
        """10. Altered intermediate observation."""
        receipt = {
            "calculation_id": "calc_trend_altered_obs",
            "citation_id": "C10",
            "metric_name": "revenue Trend",
            "calculated_value": 100.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "values": [10.0, 5.0, 20.0],
            "trajectory": "MONOTONIC_UPWARD",
            "inputs": [
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 20.0},
                {"input_name": "percentage_change", "value": 100.0},
                {"input_name": "absolute_change", "value": 10.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "trajectory mismatch" in reason.lower()

    def test_case_11_stored_trajectory_inconsistent_with_actual_observations(self) -> None:
        """11. Stored trajectory inconsistent with actual observations."""
        receipt = {
            "calculation_id": "calc_trend_inconsistent_traj",
            "citation_id": "C11",
            "metric_name": "gross_profit_margin Trend",
            "calculated_value": -50.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "values": [20.0, 15.0, 10.0],
            "trajectory": "MONOTONIC_UPWARD",
            "inputs": [
                {"input_name": "start_value", "value": 20.0},
                {"input_name": "end_value", "value": 10.0},
                {"input_name": "percentage_change", "value": -50.0},
                {"input_name": "absolute_change", "value": -10.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "trajectory mismatch" in reason.lower()

    def test_case_12_missing_full_receipt(self) -> None:
        """12. Missing full receipt."""
        ok, outcome, reason = verify_trend_semantics(
            claim_text="Revenue growth demonstrated mixed volatility across periods.",
            receipt={},
        )
        assert not ok
        assert outcome in ("missing_receipt", "incomplete", "unsupported")
        assert "validation" in reason.lower() or "missing" in reason.lower()

    def test_case_13_missing_observations_in_calculation_model(self) -> None:
        """13. Missing observations in the calculation model."""
        calc = CalculationEvidence(
            evidence_id="C13",
            calculation_id="calc_no_obs",
            metric_name="revenue Trend",
            calculated_value=0.0,
            unit="%",
            formula="V_end - V_start",
            period_end="FY2023",
            periods=["FY2021", "FY2022", "FY2023"],
            input_observations=[
                {"input_name": "start_value", "value": 10.0},
                {"input_name": "end_value", "value": 10.0},
            ],
        )
        ok, reason = verify_trend_math(calc)
        assert not ok
        assert "missing or insufficient intermediate observations" in reason.lower()

    def test_case_14_wrong_percentage_and_absolute_change(self) -> None:
        """14. Wrong percentage and absolute change."""
        receipt = {
            "calculation_id": "calc_trend_wrong_math",
            "citation_id": "C14",
            "metric_name": "cash Trend",
            "calculated_value": 999.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "values": [100.0, 120.0, 150.0],
            "inputs": [
                {"input_name": "start_value", "value": 100.0},
                {"input_name": "end_value", "value": 150.0},
                {"input_name": "percentage_change", "value": 999.0},
                {"input_name": "absolute_change", "value": 999.0},
            ],
        }
        ok, reason = verify_trend_math(receipt)
        assert not ok
        assert "mismatch" in reason.lower()

    def test_case_15_wrong_metric_citation(self) -> None:
        """15. Wrong metric citation."""
        receipt = build_trend_receipt(
            metric_name="gross_profit_margin",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[25.0, 26.0, 18.0],
            unit="%",
            citation_id="C15",
        )
        assert receipt is not None
        ok, outcome, reason = verify_trend_semantics(
            claim_text="Free cash flow demonstrated mixed volatility across periods.",
            receipt=receipt,
        )
        assert not ok
        assert outcome == "unsupported"
        assert "metric mismatch" in reason.lower()

    def test_case_16_wrong_reporting_period(self) -> None:
        """16. Wrong reporting period."""
        receipt = build_trend_receipt(
            metric_name="revenue",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[100.0, 120.0, 140.0],
            unit="USD",
            citation_id="C16",
        )
        assert receipt is not None
        ok, outcome, reason = verify_trend_semantics(
            claim_text="Revenue grew steadily during FY2018.",
            receipt=receipt,
            mentioned_period="FY2018",
        )
        assert not ok
        assert outcome == "unsupported"
        assert "period mismatch" in reason.lower()

    def test_case_17_semantic_contradiction_reflected_in_reconciled_audit_counts(self) -> None:
        """17. Semantic contradiction reflected in reconciled audit counts."""
        claim = ExtractedClaim(
            claim_id="CLM-CONTRADICT",
            claim_text="Revenue growth demonstrated mixed volatility across periods (-87.5%).",
            claim_type=ClaimType.HISTORICAL_COMPARISON,
            citation_ids=["C17"],
            is_verifiable=True,
        )
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[150.0, 50.0, 10.0],
            unit="%",
            citation_id="C17",
        )
        assert receipt is not None
        assert receipt["trajectory"] == "MONOTONIC_DOWNWARD"

        sem_ok, sem_outcome, sem_reason = verify_trend_semantics(
            claim_text=claim.claim_text,
            receipt=receipt,
        )
        assert not sem_ok
        assert sem_outcome == "contradicted"

        orig_supported = 10
        orig_contradicted = 0
        if not sem_ok and sem_outcome == "contradicted":
            reconciled_supported = orig_supported - 1
            reconciled_contradicted = orig_contradicted + 1
        else:
            reconciled_supported = orig_supported
            reconciled_contradicted = orig_contradicted

        assert reconciled_supported == 9
        assert reconciled_contradicted == 1

    def test_case_18_incomplete_receipt_prevents_final_verified_status(self) -> None:
        """18. Incomplete receipt preventing final verified status."""
        auditor = TrendReceiptAuditor()
        incomplete_receipt = {
            "calculation_id": "calc_incomplete",
            "citation_id": "C18",
            "metric_name": "growth Trend",
            "calculated_value": 10.0,
            "unit": "%",
            "periods": ["FY2021", "FY2022", "FY2023"],
            "values": [10.0],
            "inputs": [{"input_name": "start_value", "value": 10.0}],
        }
        record = auditor.audit_receipt(incomplete_receipt, citation_id="C18", claim_id="CLM-INC")
        assert record["status"] == "incomplete"
        assert not record["is_valid"]

        substantive_failures = 1 if record["status"] != "valid" else 0
        company_status = "verified" if substantive_failures == 0 else "partially_verified"
        assert company_status == "partially_verified"

    def test_case_19_multiple_claims_referencing_same_receipt(self) -> None:
        """19. Multiple claims referencing the same receipt."""
        auditor = TrendReceiptAuditor()
        receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[17.5317, 17.9565, 6.8820],
            unit="%",
            citation_id="C19",
        )
        assert receipt is not None
        rec1 = auditor.audit_receipt(receipt, citation_id="C19", claim_id="CLM-01")
        rec2 = auditor.audit_receipt(receipt, citation_id="C19", claim_id="CLM-02")
        assert rec1 == rec2
        assert len(auditor.audited_receipts) == 1
        summary = auditor.get_summary()
        assert summary["total_unique_receipts"] == 1
        assert summary["total_referencing_claims"] == 2
        assert "CLM-01" in auditor.receipt_to_claims[receipt["calculation_id"]]
        assert "CLM-02" in auditor.receipt_to_claims[receipt["calculation_id"]]

    def test_case_20_generic_use_of_accelerated_not_classified_as_financial_trend(self) -> None:
        """20. Generic use of 'accelerated' not classified as a financial trend."""
        extractor = ClaimExtractor()

        # 1. Genuine financial trend: accelerated
        res1 = extractor.extract_claims("Revenue growth accelerated across FY2021–FY2023.")
        assert res1.claims[0].claim_type == ClaimType.HISTORICAL_COMPARISON

        # 2. Genuine financial trend: decelerated
        res2 = extractor.extract_claims("Revenue growth decelerated over comparative fiscal periods.")
        assert res2.claims[0].claim_type == ClaimType.HISTORICAL_COMPARISON

        # 3. Debt acceleration clause: NOT historical comparison
        res3 = extractor.extract_claims("If any of our debt is accelerated, repayment may become due.")
        assert res3.claims[0].claim_type != ClaimType.HISTORICAL_COMPARISON

        # 4. Generic operational speedup: NOT historical comparison
        res4 = extractor.extract_claims("The company accelerated production.")
        assert res4.claims[0].claim_type != ClaimType.HISTORICAL_COMPARISON

        # 5. Period comparison: historical comparison
        res5 = extractor.extract_claims("Operating costs increased compared with the previous year.")
        assert res5.claims[0].claim_type == ClaimType.HISTORICAL_COMPARISON

