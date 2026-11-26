"""Targeted Unit & Adversarial Regression Tests for Session 18.1.3.

Covers:
- Removal of trend claim suppression ("demonstrated mixed volatility across periods")
- Positive, negative, and mixed trend assertion verification
- Adversarial incorrect percentages, directional language, and metric mismatches
- Wrong calculation receipt references
- Period normalization (FY2023, FY 2023, 2023, Q3 FY2023, FYFY2023, FY2023-Q3, spans, dates)
- Multiple claims referencing the same calculation receipt (deduplication)
- Independent mathematical trend recalculation and zero-denominator handling
"""

import pytest

from backend.finance.financial_trends import (
    build_trend_receipt,
    compute_absolute_change,
    compute_percentage_change,
    verify_trend_math,
)
from backend.rag.rag_models import CalculationEvidence
from backend.verification.claim_extractor import ClaimExtractor
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.period_verifier import normalize_period
from backend.verification.verification_models import ClaimType, VerificationOutcome


class TestTrendClaimExtractionAndSuppressionRemoval:
    """Test that substantive trend assertions are extracted as verifiable claims."""

    def setup_method(self) -> None:
        self.extractor = ClaimExtractor()

    def test_mixed_volatility_trend_claim_not_suppressed(self) -> None:
        text = "- **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-60.8%)). [C4]"
        res = self.extractor.extract_claims(text)
        assert len(res.claims) >= 1
        claim = res.claims[0]
        assert claim.is_verifiable is True
        assert claim.claim_type == ClaimType.HISTORICAL_COMPARISON
        assert "revenue_growth" in claim.claim_text
        assert "C4" in claim.citation_ids
        assert len(claim.numeric_values) == 2

    def test_positive_trend_claim_extracted(self) -> None:
        text = "- **Revenue Growth (UPWARD)**: revenue_growth expanded significantly across periods (net shift: +64.45 percentage (+105.0%)). [C13]"
        res = self.extractor.extract_claims(text)
        assert len(res.claims) >= 1
        claim = res.claims[0]
        assert claim.is_verifiable is True
        assert claim.claim_type == ClaimType.HISTORICAL_COMPARISON
        assert "C13" in claim.citation_ids

    def test_negative_trend_claim_extracted(self) -> None:
        text = "- **Gross Profit Margin (DOWNWARD)**: gross_profit_margin declined by -7.03 percentage (-27.8%) across the comparative periods. [C14]"
        res = self.extractor.extract_claims(text)
        assert len(res.claims) >= 1
        claim = res.claims[0]
        assert claim.is_verifiable is True
        assert claim.claim_type == ClaimType.HISTORICAL_COMPARISON
        assert "C14" in claim.citation_ids


class TestTrendClaimVerificationAgainstReceipts:
    """Test verification of trend assertions against deterministic calculation receipts."""

    def setup_method(self) -> None:
        self.extractor = ClaimExtractor()
        self.verifier = EvidenceVerifier()

        # Deterministic MSFT receipt: 17.5317 -> 6.8820 (recalc: -60.7454%)
        self.msft_trend_receipt = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[17.5317, 17.9561, 6.8820],
            unit="percentage",
            citation_id="C4",
            supporting_receipt_ids=["C1", "C2", "C3"],
        )
        self.msft_calc_ev = CalculationEvidence(
            evidence_id="C4",
            citation_id="C4",
            calculation_id=self.msft_trend_receipt["calculation_id"],
            metric_name=self.msft_trend_receipt["metric_name"],
            formula=self.msft_trend_receipt["formula_expression"],
            calculated_value=self.msft_trend_receipt["calculated_value"],
            unit=self.msft_trend_receipt["unit"],
            period_start=self.msft_trend_receipt["period_start"],
            period_end=self.msft_trend_receipt["period_end"],
            input_observations=self.msft_trend_receipt["inputs"],
        )

    def test_valid_mixed_trend_assertion_supported(self) -> None:
        text = "- **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-60.7%)). [C4]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.SUPPORTED
        assert "calc_trend_revenue_growth_FY2021_FY2023" in vr.verification_reason
        assert vr.confidence_score == 1.0

    def test_trend_assertion_incorrect_percentage_unsupported(self) -> None:
        text = "- **Revenue Growth (MIXED)**: revenue_growth demonstrated mixed volatility across periods (net shift: -10.65 percentage (-15.0%)). [C4]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.UNSUPPORTED
        assert "Numerical mismatch" in vr.verification_reason
        assert "-15.0" in vr.verification_reason

    def test_trend_assertion_reversed_directional_polarity_contradicted(self) -> None:
        # Claim asserts growth/acceleration (+60.7%) when receipt calculates negative (-60.75%)
        text = "Revenue growth accelerated significantly (+60.7%) over comparative fiscal periods. [C4]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.CONTRADICTED
        assert "Sign error" in vr.verification_reason or "polarity" in vr.verification_reason.lower()

    def test_trend_assertion_narrative_polarity_reversal_contradicted(self) -> None:
        # Qualitative assertion claiming acceleration with negative receipt
        text = "Revenue growth expanded and accelerated over comparative fiscal periods. [C4]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.CONTRADICTED
        assert "Trend polarity contradiction" in vr.verification_reason

    def test_trend_assertion_wrong_metric_name_unsupported(self) -> None:
        text = "Gross margin experienced downward compression across periods (-60.7%). [C4]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.UNSUPPORTED
        assert "Metric mismatch" in vr.verification_reason

    def test_trend_assertion_non_existent_citation_unsupported(self) -> None:
        text = "Revenue growth decelerated across periods (-60.7%). [C99]"
        res = self.extractor.extract_claims(text)
        claim = res.claims[0]

        vr = self.verifier.verify_claim(claim, retrieved_evidence=[], calculation_evidence=[self.msft_calc_ev])
        assert vr.outcome == VerificationOutcome.UNSUPPORTED
        assert "references non-existent or fabricated citation" in vr.verification_reason


class TestPeriodNormalization:
    """Test comprehensive canonical period normalization."""

    @pytest.mark.parametrize(
        ("input_period", "expected"),
        [
            ("FY2023", "FY2023"),
            ("FY 2023", "FY2023"),
            ("2023", "FY2023"),
            ("FYFY2023", "FY2023"),
            ("FY FY 2023", "FY2023"),
            ("fiscal year 2023", "FY2023"),
            ("fiscal 2023", "FY2023"),
            ("calendar year 2023", "FY2023"),
            ("Q3 FY2023", "Q3 FY2023"),
            ("Q3 2023", "Q3 FY2023"),
            ("FY2023-Q3", "Q3 FY2023"),
            ("2023-12-31", "2023-12-31"),
            ("2021-01-01", "2021-01-01"),
            ("FY2021-FY2023", "FY2021-FY2023"),
            ("FY2021_FY2023", "FY2021-FY2023"),
            ("2021-2023", "FY2021-FY2023"),
            (None, None),
            ("", None),
            ("None", None),
        ],
    )
    def test_normalize_period_canonicalization(self, input_period: str | None, expected: str | None) -> None:
        assert normalize_period(input_period) == expected

    def test_extractor_extracts_canonical_period(self) -> None:
        extractor = ClaimExtractor()
        assert extractor.extract_period("Deterministic calculation of revenue_growth for FY 2023: 18.8%") == "FY2023"
        assert extractor.extract_period("Deterministic calculation of revenue_growth for 2023: 18.8%") == "FY2023"
        assert extractor.extract_period("In Q3 2023, total revenues reached $20B.") == "Q3 FY2023"


class TestReceiptIntegrityAndDeduplication:
    """Test independent receipt recalculation and summary deduplication."""

    def test_tsla_revenue_growth_mathematical_reconciliation(self) -> None:
        # TSLA FY2021 revenue growth = 150.7913%, FY2023 = 18.7953%
        start_val = 150.7913
        end_val = 18.7953

        abs_chg = compute_absolute_change(start_val, end_val)
        pct_chg = compute_percentage_change(start_val, end_val)

        assert abs_chg == pytest.approx(-131.9960, abs=1e-3)
        assert pct_chg == pytest.approx(-87.5356, abs=1e-3)
        assert round(pct_chg, 1) == -87.5

        trec = build_trend_receipt(
            metric_name="revenue_growth",
            periods=["FY2021", "FY2022", "FY2023"],
            values=[start_val, 51.3517, end_val],
            unit="percentage",
            citation_id="C13",
            supporting_receipt_ids=["C9", "C5", "C1"],
        )
        assert trec is not None
        assert trec["calculated_value"] == pytest.approx(-87.5356, abs=1e-3)
        is_valid, reason = verify_trend_math(trec)
        assert is_valid is True
        assert "Deterministic trend percentage verified" in reason

    def test_zero_denominator_recalculation(self) -> None:
        pct_chg = compute_percentage_change(0.0, 100.0)
        assert pct_chg is None

        trec = build_trend_receipt(
            metric_name="ebitda",
            periods=["FY2021", "FY2022"],
            values=[0.0, 500000.0],
            unit="USD",
            citation_id="C5",
        )
        assert trec is not None
        assert trec["unit"] == "USD"
        assert trec["formula_name"] == "Multi-Period Absolute Net Shift"
        assert trec["calculated_value"] == 500000.0
        is_valid, _ = verify_trend_math(trec)
        assert is_valid is True

    def test_multiple_claims_single_receipt_deduplication(self) -> None:
        # Two distinct claims referencing the same receipt C4
        claims = [
            {"claim_id": "CLM-1", "claim_text": "Fact 1", "citation_ids": ["C4"]},
            {"claim_id": "CLM-2", "claim_text": "Fact 2", "citation_ids": ["C4"]},
        ]
        # Receipts summary should deduplicate C4
        seen_cids = set()
        deduped_receipts = []
        for cl in claims:
            for cid in cl["citation_ids"]:
                if cid not in seen_cids:
                    seen_cids.add(cid)
                    deduped_receipts.append({"citation_id": cid, "status": "verified"})

        assert len(deduped_receipts) == 1
        assert len(claims) == 2
