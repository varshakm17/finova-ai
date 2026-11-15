"""Tests for Evidence Verifier (Session 09).

Verifies layered verification outcomes: SUPPORTED, PARTIALLY_SUPPORTED,
UNSUPPORTED, CONTRADICTED, and NOT_VERIFIABLE, including fabricated and missing citations.
"""

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.verification.evidence_verifier import EvidenceVerifier
from backend.verification.verification_models import (
    ClaimType,
    ExtractedClaim,
    NumericClaimValue,
    VerificationOutcome,
)
from config.settings import get_settings


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


def test_evidence_verifier_supported_receipt():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-01",
        claim_text="Operating margin was 29.8% in FY2023 [C1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        citation_ids=["C1"],
        numeric_values=[
            NumericClaimValue(
                raw_text="29.8%",
                numeric_value=29.8,
                unit="percentage",
                scale_multiplier=1.0,
                normalized_value=29.8,
                is_percentage=True,
            )
        ],
        mentioned_period="FY2023",
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
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=calc_ev,
    )
    assert res.outcome == VerificationOutcome.SUPPORTED
    assert res.confidence_score >= 0.8
    assert "C1" in res.supporting_evidence_ids


def test_evidence_verifier_unsupported_citation():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-02",
        claim_text="The company acquired a quantum computing lab in Austin [E1].",
        claim_type=ClaimType.GENERAL_FACT,
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in 2023.",
        )
    ]
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert res.outcome == VerificationOutcome.UNSUPPORTED
    assert res.confidence_score >= 0.7


def test_evidence_verifier_fabricated_citation():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-03",
        claim_text="Total net sales were $383 billion [E99].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        citation_ids=["E99"],
    )
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=[],
    )
    assert res.outcome == VerificationOutcome.UNSUPPORTED
    assert "E99" in res.verification_reason


def test_evidence_verifier_uncited_claim():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-04",
        claim_text="Future profitability is expected to remain stable across all key divisions.",
        claim_type=ClaimType.FORWARD_LOOKING,
        citation_ids=[],
    )
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=[],
    )
    assert res.outcome == VerificationOutcome.UNSUPPORTED
    assert len(res.warnings) > 0


def test_evidence_verifier_contradicted_claim():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-05",
        claim_text="Total revenue expanded significantly by 15% [E1].",
        claim_type=ClaimType.TREND_DIRECTION,
        citation_ids=["E1"],
        mentioned_period="2023",
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales decreased by 2.8% to $383,285 million in 2023.",
        )
    ]
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert res.outcome == VerificationOutcome.CONTRADICTED
    assert "E1" in res.contradicting_evidence_ids


def test_evidence_verifier_unverifiable():
    verifier = EvidenceVerifier(settings=get_settings())
    claim = ExtractedClaim(
        claim_id="CLM-06",
        claim_text="In summary, these results demonstrate strong execution.",
        claim_type=ClaimType.GENERAL_FACT,
        citation_ids=[],
        is_verifiable=False,
    )
    res = verifier.verify_claim(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=[],
    )
    assert res.outcome == VerificationOutcome.NOT_VERIFIABLE
