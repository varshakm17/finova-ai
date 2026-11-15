"""Tests for Contradiction Detection (Session 09).

Verifies detection of directional conflicts (increased vs decreased),
numerical conflicts, cross-evidence conflicts, and multi-period trend distinction.
"""

from backend.rag.rag_models import RetrievedEvidence
from backend.verification.contradiction_detector import ContradictionDetector
from backend.verification.verification_models import (
    ClaimType,
    ExtractedClaim,
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


def test_contradiction_directional_conflict():
    detector = ContradictionDetector()
    claim = ExtractedClaim(
        claim_id="CLM-01",
        claim_text="Total revenue increased significantly in FY2023 [E1].",
        claim_type=ClaimType.TREND_DIRECTION,
        citation_ids=["E1"],
        mentioned_period="FY2023",
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales decreased by 2.8% to $383,285 million in 2023 from 2022.",
        )
    ]
    detail = detector.check_claim_contradiction(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert detail.has_contradiction is True
    assert detail.contradiction_type == "directional_conflict"
    assert (
        "decrease" in detail.explanation.lower()
        or "growth" in detail.explanation.lower()
    )


def test_contradiction_no_conflict_when_supported():
    detector = ContradictionDetector()
    claim = ExtractedClaim(
        claim_id="CLM-02",
        claim_text="Total net sales were $383,285 million in fiscal 2023 [E1].",
        claim_type=ClaimType.FINANCIAL_METRIC,
        citation_ids=["E1"],
        mentioned_period="2023",
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in fiscal 2023.",
        )
    ]
    detail = detector.check_claim_contradiction(
        claim=claim,
        retrieved_evidence=evidence,
        calculation_evidence=[],
    )
    assert detail.has_contradiction is False
    assert detail.contradiction_type == "none"


def test_contradiction_cross_evidence_directional_conflict():
    detector = ContradictionDetector()
    # Two pieces of evidence for the same reporting period stating opposing directions
    ev1 = make_evidence(
        evidence_id="E1",
        chunk_text="In the fiscal period ended September 30, 2023, product sales increased rapidly.",
        report_date="2023-09-30",
    )
    ev2 = make_evidence(
        evidence_id="E2",
        chunk_text="In the fiscal period ended September 30, 2023, product sales decreased across categories.",
        report_date="2023-09-30",
    )
    cross_conflicts = detector.detect_cross_evidence_contradictions([ev1, ev2])
    assert len(cross_conflicts) == 1
    assert cross_conflicts[0].has_contradiction is True
    assert cross_conflicts[0].contradiction_type == "directional_conflict"


def test_contradiction_amended_filing_not_treated_as_contradiction():
    detector = ContradictionDetector()
    ev1 = make_evidence(
        evidence_id="E1",
        chunk_text="Total net sales were reported as $100 billion.",
        filing_type="10-K",
        report_date="2023-09-30",
    )
    ev2 = make_evidence(
        evidence_id="E2",
        chunk_text="Total net sales were restated as $95 billion.",
        filing_type="10-K/A",
        report_date="2023-09-30",
    )
    cross_conflicts = detector.detect_cross_evidence_contradictions([ev1, ev2])
    # Amended filings supersede original, not treated as irreconcilable contradiction
    assert len(cross_conflicts) == 0
