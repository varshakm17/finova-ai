"""Integration tests for Session 09 Anti-Hallucination & Verification API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.rag.rag_models import (
    Citation,
    RAGAnswer,
    RetrievedEvidence,
)
from backend.verification.verification_models import (
    ClaimVerificationResult,
    OverallVerificationStatus,
    VerificationOutcome,
    VerificationRun,
)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def sample_verification_run(
    run_id: str = "vrun_test123", answer_id: str = "ans_test123"
) -> VerificationRun:
    return VerificationRun(
        run_id=run_id,
        answer_id=answer_id,
        overall_status=OverallVerificationStatus.VERIFIED,
        total_claims=1,
        supported_claims=1,
        partially_supported_claims=0,
        unsupported_claims=0,
        contradicted_claims=0,
        not_verifiable_claims=0,
        claim_results=[
            ClaimVerificationResult(
                claim_id="clm_01",
                claim_text="Total revenue was $383,285 million [E1].",
                outcome=VerificationOutcome.SUPPORTED,
                supporting_evidence_ids=["E1"],
                verification_reason="Statutory match in E1.",
                confidence_score=0.95,
                verification_method="deterministic_receipt",
            )
        ],
        contradictions=[],
        numeric_mismatches=[],
        period_mismatches=[],
        warnings=[],
    )


def sample_rag_answer(answer_id: str = "ans_test123") -> RAGAnswer:
    return RAGAnswer(
        answer_id=answer_id,
        question="What was Apple's revenue?",
        answer="Total revenue was $383,285 million in FY2023 [E1].",
        answer_status="answered",
        citations=[
            Citation(
                citation_id="E1",
                evidence_type="filing_passage",
                source_reference="AAPL 10-K",
                source_url="https://www.sec.gov/edgar",
                excerpt="Total net sales was $383,285 million.",
            )
        ],
        retrieved_evidence=[
            RetrievedEvidence(
                evidence_id="E1",
                chunk_id="chk_01",
                ticker="AAPL",
                company_name="Apple Inc.",
                filing_type="10-K",
                filing_date="2023-11-03",
                report_date="2023-09-30",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_7",
                section_title="MD&A",
                chunk_text="Total net sales was $383,285 million.",
                source_url="https://www.sec.gov/edgar",
            )
        ],
        calculation_evidence=[],
        model_name="mock-model",
        provider="mock",
        retrieval_method="hybrid",
        generation_metadata={},
        warnings=[],
    )


def test_api_get_verification_run_success(client: TestClient):
    vrun = sample_verification_run()
    with patch(
        "backend.api.routes._verification_service.get_latest_verification_for_answer",
        return_value=vrun,
    ):
        resp = client.get(f"/api/v1/research/answers/{vrun.answer_id}/verification")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == vrun.run_id
        assert data["overall_status"] == "verified"
        assert data["total_claims"] == 1


def test_api_get_verification_run_not_found(client: TestClient):
    with patch(
        "backend.api.routes._verification_service.get_latest_verification_for_answer",
        return_value=None,
    ):
        resp = client.get("/api/v1/research/answers/ans_missing/verification")
        assert resp.status_code == 404
        assert "not found" in resp.json()["message"].lower()


def test_api_post_verify_answer_success(client: TestClient):
    ans = sample_rag_answer()
    vrun = sample_verification_run()
    with (
        patch("backend.api.routes._rag_service.get_answer", return_value=ans),
        patch(
            "backend.api.routes._verification_service.verify_answer", return_value=vrun
        ),
    ):
        resp = client.post(f"/api/v1/research/answers/{ans.answer_id}/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == vrun.run_id
        assert data["overall_status"] == "verified"


def test_api_post_verify_answer_not_found(client: TestClient):
    with patch("backend.api.routes._rag_service.get_answer", return_value=None):
        resp = client.post("/api/v1/research/answers/ans_missing/verify")
        assert resp.status_code == 404


def test_api_capabilities_includes_verification(client: TestClient):
    resp = client.get("/api/v1/research/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_engine_enabled"] is True
    assert "verification_version" in data
