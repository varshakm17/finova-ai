"""Tests for Period Consistency Verification (Session 09).

Verifies matching of fiscal years, detection of temporal divergence (FY2022 vs FY2023),
filing frequency mismatch (10-K vs 10-Q), and quarterly confusion (Q1 vs Q3).
"""

from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.verification.period_verifier import PeriodVerifier
from backend.verification.verification_models import ClaimType, ExtractedClaim


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


def test_period_verifier_exact_match():
    verifier = PeriodVerifier()
    claim = ExtractedClaim(
        claim_id="CLM-01",
        claim_text="Total revenue was strong in FY2023 [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        mentioned_period="FY2023",
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            filing_date="2023-11-03",
            report_date="2023-09-30",
        )
    ]
    det = verifier.verify_claim_period(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert det.is_consistent is True
    assert det.mismatch_type == "none"


def test_period_verifier_fiscal_year_mismatch():
    verifier = PeriodVerifier()
    claim = ExtractedClaim(
        claim_id="CLM-02",
        claim_text="Revenue grew strongly in FY2023 [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        mentioned_period="FY2023",
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            filing_date="2022-10-28",
            report_date="2022-09-24",
        )
    ]
    det = verifier.verify_claim_period(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert det.is_consistent is False
    assert det.mismatch_type == "fiscal_year_mismatch"


def test_period_verifier_frequency_mismatch():
    verifier = PeriodVerifier()
    # Claim states annual period, but cited evidence is 10-Q quarterly filing
    claim = ExtractedClaim(
        claim_id="CLM-03",
        claim_text="For the full annual period FY2023, net sales grew [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        mentioned_period="annual FY2023",
        citation_ids=["E1"],
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            filing_type="10-Q",
            filing_date="2023-05-05",
            report_date="2023-04-01",
        )
    ]
    det = verifier.verify_claim_period(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert det.is_consistent is False
    assert det.mismatch_type == "annual_vs_quarterly"


def test_period_verifier_quarter_mismatch():
    verifier = PeriodVerifier()
    claim = ExtractedClaim(
        claim_id="CLM-04",
        claim_text="During Q1 2023, sales grew [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        mentioned_period="Q1 2023",
        citation_ids=["E1"],
    )
    # Evidence text states Q3
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="During the third quarter Q3 2023, sales were $81.8 billion.",
            filing_type="10-Q",
            filing_date="2023-08-04",
            report_date="2023-07-01",
        )
    ]
    det = verifier.verify_claim_period(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert det.is_consistent is False
    assert det.mismatch_type == "quarter_mismatch"


def test_period_verifier_calculation_period_match():
    verifier = PeriodVerifier()
    claim = ExtractedClaim(
        claim_id="CLM-05",
        claim_text="Operating margin was 29.8% in FY2023 [C1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        mentioned_period="FY2023",
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
    det = verifier.verify_claim_period(
        claim=claim,
        retrieved_evidence=[],
        calculation_evidence=calc_ev,
    )
    assert det.is_consistent is True
    assert det.mismatch_type == "none"
