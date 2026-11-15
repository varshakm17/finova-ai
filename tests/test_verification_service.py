"""Tests for Verification Service Orchestrator (Session 09).

Verifies end-to-end verification workflows, decision logic, status hierarchies
(VERIFIED, VERIFIED_WITH_WARNINGS, PARTIALLY_VERIFIED, REJECTED, INCONCLUSIVE),
and relational database persistence in SQLite.
"""

import tempfile
from pathlib import Path

import pytest

from backend.data.storage import Database
from backend.rag.rag_models import CalculationEvidence, RetrievedEvidence
from backend.verification.verification_models import OverallVerificationStatus
from backend.verification.verification_service import VerificationService
from config.settings import get_settings


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_finova.db"
        db = Database(db_path=db_path)
        yield db


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


def test_verification_service_all_supported_verified(temp_db):
    service = VerificationService(database=temp_db, settings=get_settings())
    answer_text = (
        "In fiscal 2023, Apple reported total net sales of $383,285 million [E1]. "
        "The company recorded an operating margin of 29.8% [C1]."
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in fiscal 2023.",
            filing_date="2023-11-03",
            report_date="2023-09-30",
        )
    ]
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

    vrun = service.verify_answer(
        answer_id="ans_test_1",
        question="What were Apple's sales and operating margin in 2023?",
        answer_text=answer_text,
        retrieved_evidence=evidence,
        calculation_evidence=calc_ev,
        persist=True,
    )

    assert vrun.overall_status in (
        OverallVerificationStatus.VERIFIED,
        OverallVerificationStatus.VERIFIED_WITH_WARNINGS,
    )
    assert vrun.total_claims == 2
    assert vrun.supported_claims == 2
    assert vrun.unsupported_claims == 0
    assert vrun.contradicted_claims == 0

    # Test retrieval from database
    fetched = service.get_latest_verification_for_answer("ans_test_1")
    assert fetched is not None
    assert fetched.run_id == vrun.run_id
    assert fetched.total_claims == 2

    # Test retrieval by run_id
    fetched_by_id = service.get_verification_run(vrun.run_id)
    assert fetched_by_id is not None
    assert fetched_by_id.run_id == vrun.run_id


def test_verification_service_contradicted_rejected(temp_db):
    service = VerificationService(database=temp_db, settings=get_settings())
    answer_text = "Apple's net sales grew strongly in fiscal 2023 [E1]."
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales decreased by 2.8% to $383,285 million in 2023.",
        )
    ]

    vrun = service.verify_answer(
        answer_id="ans_test_2",
        question="Did Apple grow in 2023?",
        answer_text=answer_text,
        retrieved_evidence=evidence,
        calculation_evidence=[],
        persist=True,
    )

    assert vrun.overall_status == OverallVerificationStatus.REJECTED
    assert vrun.contradicted_claims >= 1
    assert len(vrun.contradictions) >= 1


def test_verification_service_partially_verified(temp_db):
    service = VerificationService(database=temp_db, settings=get_settings())
    # 1 supported claim, 1 unsupported claim
    answer_text = (
        "Apple reported total net sales of $383,285 million in 2023 [E1]. "
        "The company also announced plans to launch flying cars by 2025 [E1]."
    )
    evidence = [
        make_evidence(
            evidence_id="E1",
            chunk_text="Total net sales were $383,285 million in fiscal 2023.",
            filing_date="2023-11-03",
            report_date="2023-09-30",
        )
    ]

    vrun = service.verify_answer(
        answer_id="ans_test_3",
        question="What did Apple report?",
        answer_text=answer_text,
        retrieved_evidence=evidence,
        calculation_evidence=[],
        persist=True,
    )

    assert vrun.overall_status == OverallVerificationStatus.PARTIALLY_VERIFIED
    assert vrun.supported_claims == 1
    assert vrun.unsupported_claims == 1


def test_verification_service_inconclusive(temp_db):
    service = VerificationService(database=temp_db, settings=get_settings())
    answer_text = "The available SEC filing disclosures do not provide sufficient evidence to answer this question."

    vrun = service.verify_answer(
        answer_id="ans_test_4",
        question="What was the dark matter expenditure?",
        answer_text=answer_text,
        retrieved_evidence=[],
        calculation_evidence=[],
        persist=True,
    )

    assert vrun.overall_status == OverallVerificationStatus.INCONCLUSIVE
