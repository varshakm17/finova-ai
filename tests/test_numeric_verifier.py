"""Tests for Numeric Verification (Session 09).

Tests tolerance verification, scale error detection (thousands vs millions),
percentage vs fraction handling, sign mismatch, and calculation receipt matching.
"""

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.verification.numeric_verifier import NumericVerifier
from backend.verification.verification_models import (
    ClaimType,
    ExtractedClaim,
    NumericClaimValue,
)


def make_evidence(
    evidence_id: str = "E1",
    chunk_text: str = "Sample passage text",
    ticker: str = "AAPL",
    filing_type: str = "10-K",
    filing_date: str = "2023-11-03",
    report_date: str | None = "2023-09-30",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        evidence_id=evidence_id,
        chunk_id=f"chk_{evidence_id}",
        ticker=ticker,
        company_name="Apple Inc.",
        filing_type=filing_type,
        filing_date=filing_date,
        report_date=report_date,
        accession_number="0000320193-23-000106",
        section_identifier="ITEM_7",
        section_title="MD&A",
        chunk_text=chunk_text,
        source_url="https://www.sec.gov/edgar",
    )


def test_numeric_verifier_exact_match():
    verifier = NumericVerifier(tolerance_pct=1.0)
    claim_val = NumericClaimValue(
        raw_text="$383,285 million",
        numeric_value=383285.0,
        unit="USD",
        scale_multiplier=1e6,
        normalized_value=383285000000.0,
        is_percentage=False,
    )
    claim = ExtractedClaim(
        claim_id="CLM-01",
        claim_text="Total net sales was $383,285 million [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        numeric_values=[claim_val],
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in fiscal year 2023.",
        )
    ]
    details = verifier.verify_claim_numbers(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert len(details) == 1
    assert details[0].matched is True
    assert details[0].error_type == "none"


def test_numeric_verifier_scale_error_detected():
    verifier = NumericVerifier(tolerance_pct=1.0)
    # Claim states $383,285 thousand instead of million (1000x difference)
    claim_val = NumericClaimValue(
        raw_text="$383,285 thousand",
        numeric_value=383285.0,
        unit="USD",
        scale_multiplier=1e3,
        normalized_value=383285000.0,
        is_percentage=False,
    )
    claim = ExtractedClaim(
        claim_id="CLM-02",
        claim_text="Total net sales was $383,285 thousand [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        numeric_values=[claim_val],
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in 2023.",
        )
    ]
    details = verifier.verify_claim_numbers(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert len(details) == 1
    assert details[0].matched is False
    assert details[0].error_type == "scale_error_thousands_vs_millions"


def test_numeric_verifier_percentage_fraction_handling():
    verifier = NumericVerifier(tolerance_pct=1.0)
    # Claim states 0.298 (fraction) when calculation is 29.8%
    claim_val = NumericClaimValue(
        raw_text="0.298",
        numeric_value=0.298,
        unit="ratio",
        scale_multiplier=1.0,
        normalized_value=0.298,
        is_percentage=False,
    )
    claim = ExtractedClaim(
        claim_id="CLM-03",
        claim_text="Operating margin reached 0.298 [C1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        numeric_values=[claim_val],
        citation_ids=["C1"],
    )
    calc_ev = [
        CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_1",
            metric_name="operating_margin",
            calculated_value=29.8,
            unit="percentage",
            formula="operating_income / total_revenue",
            period_end="2023-09-30",
        )
    ]
    details = verifier.verify_claim_numbers(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=calc_ev,
    )
    assert len(details) == 1
    assert details[0].matched is False
    assert details[0].error_type == "scale_error_percentage_vs_fraction"


def test_numeric_verifier_tolerance_match():
    verifier = NumericVerifier(tolerance_pct=1.0)
    # Claim states 29.8% vs calculation receipt 29.82% (diff ~0.067% < 1.0%)
    claim_val = NumericClaimValue(
        raw_text="29.8%",
        numeric_value=29.8,
        unit="percentage",
        scale_multiplier=1.0,
        normalized_value=29.8,
        is_percentage=True,
    )
    claim = ExtractedClaim(
        claim_id="CLM-04",
        claim_text="Operating margin was 29.8% [C1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        numeric_values=[claim_val],
        citation_ids=["C1"],
    )
    calc_ev = [
        CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_1",
            metric_name="operating_margin",
            calculated_value=29.82,
            unit="percentage",
            formula="operating_income / total_revenue",
            period_end="2023-09-30",
        )
    ]
    details = verifier.verify_claim_numbers(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=calc_ev,
    )
    assert len(details) == 1
    assert details[0].matched is True


def test_numeric_verifier_sign_mismatch():
    verifier = NumericVerifier(tolerance_pct=1.0)
    claim_val = NumericClaimValue(
        raw_text="15.0%",
        numeric_value=15.0,
        unit="percentage",
        scale_multiplier=1.0,
        normalized_value=15.0,
        is_percentage=True,
    )
    claim = ExtractedClaim(
        claim_id="CLM-05",
        claim_text="Operating margin grew 15.0% [C1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        numeric_values=[claim_val],
        citation_ids=["C1"],
    )
    calc_ev = [
        CalculationEvidence(
            evidence_id="C1",
            calculation_id="calc_1",
            metric_name="operating_margin",
            calculated_value=-15.0,
            unit="percentage",
            formula="operating_income / total_revenue",
            period_end="2023-09-30",
        )
    ]
    details = verifier.verify_claim_numbers(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=calc_ev,
    )
    assert len(details) == 1
    assert details[0].matched is False
    assert details[0].error_type == "sign_mismatch"
