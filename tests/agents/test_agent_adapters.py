"""Tests for individual Finova agent adapters."""

from unittest.mock import MagicMock

from backend.agents.financial_analyst_agent import FinancialAnalystAgent
from backend.agents.rag_agent import RAGAgent
from backend.agents.research_agent import ResearchAgent
from backend.agents.state import FinovaAgentState
from backend.agents.verification_agent import VerificationAgent
from backend.finance.calculation_models import (
    CalculationReceipt,
    CalculationSummaryResponse,
)
from backend.retrieval.retrieval_models import HybridSearchResponse, HybridSearchResult
from backend.verification.verification_models import (
    OverallVerificationStatus,
    VerificationRun,
)


def test_research_agent_with_results():
    mock_search = MagicMock()
    mock_search.search.return_value = HybridSearchResponse(
        query="business risks",
        retrieval_mode="hybrid_rrf",
        status="success",
        total_results=1,
        results=[
            HybridSearchResult(
                chunk_id="chunk_123",
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                accession_number="0000320193-23-000106",
                filing_type="10-K",
                filing_date="2023-11-03",
                section_identifier="ITEM_1A",
                section_title="Risk Factors",
                chunk_text="Supply chain disruptions could affect manufacturing operations.",
                source_url="https://www.sec.gov",
                retrieval_sources=["hybrid"],
                rrf_score=0.033,
            )
        ],
        diagnostics={},
        warnings=[],
    )
    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = lambda query, candidates, top_k: (
        [
            MagicMock(
                chunk_id=candidates[0].chunk_id,
                chunk_text=candidates[0].chunk_text,
                section_identifier=candidates[0].section_identifier,
                accession_number=candidates[0].accession_number,
                filing_date=candidates[0].filing_date,
                company_name=candidates[0].company_name,
                ticker=candidates[0].ticker,
                cik=candidates[0].cik,
                rerank_score=0.92,
                original_rank=1,
            )
        ],
        {"status": "ok"},
    )

    agent = ResearchAgent(hybrid_search_service=mock_search, reranker=mock_reranker)
    state: FinovaAgentState = {
        "user_question": "What are Apple business risks?",
        "company_ticker": "AAPL",
    }
    result = agent.execute(state)
    assert len(result["retrieved_evidence"]) == 1
    assert result["retrieved_evidence"][0]["chunk_id"] == "chunk_123"
    assert result["current_step"] == "research_agent"


def test_research_agent_empty_results():
    mock_search = MagicMock()
    mock_search.search.return_value = HybridSearchResponse(
        query="empty query",
        retrieval_mode="hybrid_rrf",
        status="success",
        total_results=0,
        results=[],
        diagnostics={},
        warnings=[],
    )
    agent = ResearchAgent(hybrid_search_service=mock_search)
    state: FinovaAgentState = {"user_question": "Unknown facts?"}
    result = agent.execute(state)
    assert result["retrieved_evidence"] == []
    assert len(result["warnings"]) > 0


def test_financial_analyst_agent_execution():
    mock_calc = MagicMock()
    mock_receipt = CalculationReceipt(
        calculation_id="calc_1",
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        period_type="annual",
        period_end="2023-09-30",
        metric_name="gross_profit_margin",
        metric_display_name="Gross Profit Margin",
        fiscal_year=2023,
        fiscal_period="FY",
        calculated_value=44.13,
        unit="percentage",
        formula_name="Gross Margin Formula",
        formula_expression="Gross Profit / Total Revenue",
        formula_definition="Gross Profit / Total Revenue",
        status="calculated",
        inputs=[],
        confidence_score=1.0,
        notes=[],
    )
    mock_calc.calculate_company_metrics.return_value = CalculationSummaryResponse(
        ticker="AAPL",
        cik="0000320193",
        company_name="Apple Inc.",
        period_type="annual",
        total_calculated=1,
        total_unavailable=0,
        total_invalid=0,
        calculations=[mock_receipt],
    )

    agent = FinancialAnalystAgent(calculation_service=mock_calc)
    state: FinovaAgentState = {
        "user_question": "What is the gross margin for Apple in FY2023?",
        "company_ticker": "AAPL",
        "reporting_period": "FY2023",
    }
    result = agent.execute(state)
    assert len(result["calculation_results"]) == 1
    assert result["calculation_results"][0]["metric_name"] == "gross_profit_margin"
    assert result["calculation_results"][0]["calculated_value"] == 44.13


def test_financial_analyst_agent_missing_ticker():
    agent = FinancialAnalystAgent()
    state: FinovaAgentState = {"user_question": "What is the margin?"}
    result = agent.execute(state)
    assert result["calculation_results"] == []
    assert "No ticker" in result["warnings"][0]


def test_rag_agent_mock_response():
    agent = RAGAgent()
    state: FinovaAgentState = {
        "user_question": "Analyze Apple revenue",
        "mock_llm_response": "Apple revenue was driven by iPhone and Services [C1].",
    }
    result = agent.execute(state)
    assert (
        result["generated_answer"]
        == "Apple revenue was driven by iPhone and Services [C1]."
    )


def test_rag_agent_insufficient_evidence():
    agent = RAGAgent()
    state: FinovaAgentState = {
        "user_question": "Explain random obscure event",
        "retrieved_evidence": [],
        "calculation_results": [],
    }
    result = agent.execute(state)
    assert "sufficient evidence" in result["generated_answer"]


def test_verification_agent_valid_verdict():
    mock_verifier = MagicMock()
    mock_verifier.verify_answer.return_value = VerificationRun(
        run_id="run_1",
        answer_id="ans_1",
        overall_status=OverallVerificationStatus.VERIFIED,
        total_claims=1,
        supported_claims=1,
        partially_supported_claims=0,
        unsupported_claims=0,
        contradicted_claims=0,
        not_verifiable_claims=0,
        warnings=[],
        verified_at="2026-11-15T00:00:00Z",
        verifier_version="0.1.0",
        claim_results=[],
    )

    agent = VerificationAgent(verification_service=mock_verifier)
    state: FinovaAgentState = {
        "user_question": "What was Apple gross margin?",
        "generated_answer": "Apple reported a gross profit margin of 44.13% in FY2023 [C1].",
        "calculation_results": [
            {"metric_name": "gross_profit_margin", "calculated_value": 44.13}
        ],
        "retrieved_evidence": [],
    }
    result = agent.execute(state)
    assert result["verification_result"]["is_valid"] is True
    assert result["final_answer"] is not None


def test_verification_agent_rejected_verdict():
    mock_verifier = MagicMock()
    mock_verifier.verify_answer.return_value = VerificationRun(
        run_id="run_2",
        answer_id="ans_2",
        overall_status=OverallVerificationStatus.REJECTED,
        total_claims=1,
        supported_claims=0,
        partially_supported_claims=0,
        unsupported_claims=1,
        contradicted_claims=0,
        not_verifiable_claims=0,
        warnings=["Unsupported hallucinated metric"],
        verified_at="2026-11-15T00:00:00Z",
        verifier_version="0.1.0",
        claim_results=[],
    )

    agent = VerificationAgent(verification_service=mock_verifier)
    state: FinovaAgentState = {
        "user_question": "What was Apple gross margin?",
        "generated_answer": "Apple reported a gross profit margin of 99.9% [C1].",
        "calculation_results": [],
        "retrieved_evidence": [],
    }
    result = agent.execute(state)
    assert result["verification_result"]["is_valid"] is False
    assert result["final_answer"] is None
