"""Integration tests for Session 08 RAG and LLM FastAPI endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.rag.rag_models import (
    CalculationEvidence,
    Citation,
    RAGAnswer,
    RAGCapabilitiesResponse,
    RetrievedEvidence,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def sample_rag_answer(answer_id: str = "ans_test123") -> RAGAnswer:
    return RAGAnswer(
        answer_id=answer_id,
        question="What was Apple's gross margin in FY2023?",
        answer="Apple reported a gross margin of 44.13% in FY2023 [C1], supported by product segment strength [E1].",
        answer_status="answered",
        citations=[
            Citation(
                citation_id="E1",
                evidence_type="filing_passage",
                source_reference="AAPL 10-K (2023-11-03) ITEM_7",
                source_url="https://www.sec.gov/edgar",
                excerpt="Product gross margin expanded due to favorable mix.",
            ),
            Citation(
                citation_id="C1",
                evidence_type="calculation_receipt",
                source_reference="Deterministic Calc: gross_margin = 44.13%",
                source_url="https://www.sec.gov/edgar",
                excerpt="Formula: GrossProfit / TotalRevenue",
            ),
        ],
        retrieved_evidence=[
            RetrievedEvidence(
                evidence_id="E1",
                chunk_id="chk_01",
                ticker="AAPL",
                company_name="Apple Inc.",
                filing_type="10-K",
                filing_date="2023-11-03",
                accession_number="0000320193-23-000106",
                section_identifier="ITEM_7",
                section_title="Management's Discussion and Analysis",
                chunk_text="Product gross margin expanded due to favorable mix.",
                source_url="https://www.sec.gov/edgar",
                dense_score=0.85,
                bm25_score=14.2,
                rrf_score=0.032,
                reranker_score=0.91,
            )
        ],
        calculation_evidence=[
            CalculationEvidence(
                evidence_id="C1",
                calculation_id="calc_gm_1",
                metric_name="gross_margin",
                calculated_value=44.13,
                unit="percentage",
                formula="GrossProfit / TotalRevenue",
                period_end="2023-09-30",
            )
        ],
        model_name="mock-model",
        provider="mock",
        retrieval_method="hybrid_reranked",
        generation_metadata={"latency_ms": 120.5, "tokens_generated": 35},
        warnings=[],
    )


def test_ask_endpoint_success(client: TestClient) -> None:
    expected_ans = sample_rag_answer("ans_ask_success")
    with patch(
        "backend.api.routes._rag_service.ask", return_value=expected_ans
    ) as mock_ask:
        payload = {
            "question": "What was Apple's gross margin in FY2023?",
            "ticker": "AAPL",
            "top_k": 5,
            "use_reranker": True,
            "include_calculations": True,
            "response_style": "detailed",
        }
        resp = client.post("/api/v1/research/ask", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["answer_id"] == "ans_ask_success"
        assert data["answer_status"] == "answered"
        assert len(data["citations"]) == 2
        assert data["citations"][0]["citation_id"] == "E1"
        assert data["citations"][1]["citation_id"] == "C1"
        assert data["retrieval_method"] == "hybrid_reranked"
        assert data["provider"] == "mock"
        mock_ask.assert_called_once()


def test_ask_endpoint_insufficient_evidence(client: TestClient) -> None:
    insufficient_ans = RAGAnswer(
        answer_id="ans_insuf_01",
        question="What was XYZ's profit?",
        answer="The available SEC filing disclosures and financial calculation receipts do not provide sufficient verified evidence.",
        answer_status="insufficient_evidence",
        citations=[],
        retrieved_evidence=[],
        calculation_evidence=[],
        model_name="mock-model",
        provider="mock",
        retrieval_method="hybrid",
        warnings=["Insufficient evidence threshold not met."],
    )
    with patch("backend.api.routes._rag_service.ask", return_value=insufficient_ans):
        resp = client.post(
            "/api/v1/research/ask", json={"question": "What was XYZ profit?"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer_status"] == "insufficient_evidence"
        assert len(data["citations"]) == 0


def test_get_research_answer_endpoint_success(client: TestClient) -> None:
    expected_ans = sample_rag_answer("ans_stored_01")
    with patch(
        "backend.api.routes._rag_service.get_answer", return_value=expected_ans
    ) as mock_get:
        resp = client.get("/api/v1/research/answers/ans_stored_01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer_id"] == "ans_stored_01"
        assert data["answer_status"] == "answered"
        mock_get.assert_called_once_with("ans_stored_01")


def test_get_research_answer_endpoint_not_found(client: TestClient) -> None:
    with patch("backend.api.routes._rag_service.get_answer", return_value=None):
        resp = client.get("/api/v1/research/answers/ans_nonexistent")
        assert resp.status_code == 404
        assert (
            "not found"
            in (resp.json().get("detail") or resp.json().get("message", "")).lower()
        )


def test_get_llm_status_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/llm/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data
    assert "online" in data
    assert "temperature" in data
    assert "max_tokens" in data


def test_get_research_capabilities_endpoint(client: TestClient) -> None:
    caps = RAGCapabilitiesResponse(
        supported_retrieval_modes=["dense", "sparse", "hybrid", "hybrid_reranked"],
        reranker_available=True,
        reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        calculation_engine_enabled=True,
        citation_verification_enabled=True,
        llm_provider="mock",
        llm_model="mock-model",
        llm_online=True,
    )
    with patch("backend.api.routes._rag_service.get_capabilities", return_value=caps):
        resp = client.get("/api/v1/research/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reranker_available"] is True
        assert data["calculation_engine_enabled"] is True
        assert data["citation_verification_enabled"] is True
        assert data["llm_provider"] == "mock"
        assert data["llm_online"] is True
