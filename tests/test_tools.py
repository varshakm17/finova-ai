"""Unit tests for reusable Finova agent tools."""

from unittest.mock import MagicMock

from backend.finance.calculation_models import (
    CalculationReceipt,
    CalculationSummaryResponse,
)
from backend.retrieval.retrieval_models import HybridSearchResponse
from backend.tools.calculation_tools import (
    compute_financial_metrics_tool,
    get_available_metrics_tool,
)
from backend.tools.research_tools import hybrid_search_tool
from backend.tools.verification_tools import extract_claims_tool, verify_answer_tool
from backend.verification.verification_models import (
    OverallVerificationStatus,
    VerificationRun,
)


def test_get_available_metrics_tool():
    metrics = get_available_metrics_tool()
    assert len(metrics) > 0
    assert "gross_profit_margin" in metrics
    assert "revenue_growth" in metrics


def test_compute_financial_metrics_tool():
    mock_calc = MagicMock()
    mock_receipt = CalculationReceipt(
        calculation_id="c1",
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
        formula_expression="Gross Profit / Revenue",
        formula_definition="Gross Profit / Revenue",
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

    receipts = compute_financial_metrics_tool(
        ticker="AAPL",
        metrics=["gross_profit_margin"],
        year=2023,
        calc_service=mock_calc,
    )
    assert len(receipts) == 1
    assert receipts[0]["metric_name"] == "gross_profit_margin"


def test_hybrid_search_tool():
    mock_service = MagicMock()
    mock_service.search.return_value = HybridSearchResponse(
        query="risks",
        retrieval_mode="hybrid_rrf",
        status="success",
        total_results=0,
        results=[],
        diagnostics={},
        warnings=[],
    )
    results = hybrid_search_tool(
        query="risks", ticker="AAPL", search_service=mock_service
    )
    assert results == []


def test_extract_claims_tool():
    text = "Apple recorded gross margin of 44.13% in FY2023."
    claims = extract_claims_tool(text)
    assert isinstance(claims, list)
    assert len(claims) >= 1


def test_verify_answer_tool():
    mock_verifier = MagicMock()
    mock_verifier.verify_answer.return_value = VerificationRun(
        run_id="run_tool_1",
        answer_id="ans_tool_1",
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
    res = verify_answer_tool(
        question="What was Apple gross margin?",
        answer_text="Apple recorded 44.13% gross margin [C1].",
        retrieved_evidence=[],
        calculation_evidence=[
            {"metric_name": "gross_profit_margin", "calculated_value": 44.13}
        ],
        verifier=mock_verifier,
    )
    assert res["overall_status"] == OverallVerificationStatus.VERIFIED.value
