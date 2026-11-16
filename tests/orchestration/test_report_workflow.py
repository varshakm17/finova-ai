"""Tests for Autonomous Research Report LangGraph Workflow (Session 11).

Validates end-to-end execution of the FINANCIAL_RESEARCH_REPORT multi-agent workflow:
Supervisor -> Research Planner -> Research Agent -> Financial Analyst -> Research Coordinator -> Report Agent -> Verification Agent.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock

import pytest

from backend.agents.agent_models import (
    ReportGenerationRequest,
    ReportGenerationResponse,
)
from backend.agents.financial_analyst_agent import FinancialAnalystAgent
from backend.agents.report_agent import ReportAgent
from backend.agents.research_agent import ResearchAgent
from backend.agents.research_coordinator import ResearchCoordinator
from backend.agents.research_planner import ResearchPlanner
from backend.agents.supervisor import SupervisorAgent
from backend.agents.verification_agent import VerificationAgent
from backend.data.storage import Database
from backend.orchestration.graph import FinovaOrchestrationEngine
from backend.retrieval.retrieval_models import HybridSearchResponse, HybridSearchResult


@pytest.fixture
def mock_db() -> Database:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return Database(db_path=tmp.name)


@pytest.fixture
def mock_engine(mock_db: Database) -> FinovaOrchestrationEngine:
    # Build engine with mocked backend retrieval to operate 100% offline
    mock_search = MagicMock()
    mock_search.search.return_value = HybridSearchResponse(
        query="Apple business and margins",
        retrieval_mode="hybrid_rrf",
        status="success",
        total_results=1,
        results=[
            HybridSearchResult(
                chunk_id="chunk_aapl_1",
                ticker="AAPL",
                company_name="Apple Inc.",
                cik="0000320193",
                accession_number="0000320193-23-000106",
                filing_type="10-K",
                filing_date="2023-11-03",
                section_identifier="ITEM_1",
                section_title="Business",
                chunk_text="Apple designs, manufactures and markets smartphones, personal computers, and tablets.",
                source_url="https://www.sec.gov",
                retrieval_sources=["hybrid"],
                rrf_score=0.033,
            )
        ],
        diagnostics={},
        warnings=[],
    )

    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = lambda query, candidates, top_k: (candidates, {})

    mock_calc_svc = MagicMock()
    calc_summary = MagicMock()
    calc_summary.calculations = [
        MagicMock(
            model_dump=lambda: {
                "calculation_id": "c_gm_2023",
                "ticker": "AAPL",
                "cik": "0000320193",
                "company_name": "Apple Inc.",
                "metric_name": "gross_profit_margin",
                "calculated_value": 44.13,
                "unit": "percentage",
                "period_type": "annual",
                "period_end": "2023-09-30",
                "fiscal_year": 2023,
                "fiscal_period": "FY",
                "formula_name": "Gross Profit Margin",
                "formula_expression": "(Gross Profit / Revenue) * 100",
                "status": "calculated",
                "inputs": [],
            },
            calculation_id="c_gm_2023",
            metric_name="gross_profit_margin",
            calculated_value=44.13,
            unit="percentage",
            fiscal_year=2023,
            fiscal_period="FY",
            formula_name="Gross Profit Margin",
            formula_expression="(Gross Profit / Revenue) * 100",
            status="calculated",
            company_name="Apple Inc.",
        )
    ]
    mock_calc_svc.calculate_company_metrics.return_value = calc_summary

    planner = ResearchPlanner()
    research = ResearchAgent(search_service=mock_search, cross_encoder=mock_reranker)
    analyst = FinancialAnalystAgent(calculation_service=mock_calc_svc)
    coordinator = ResearchCoordinator()
    report_agent = ReportAgent()
    verifier = VerificationAgent()
    supervisor = SupervisorAgent()

    return FinovaOrchestrationEngine(
        database=mock_db,
        supervisor_agent=supervisor,
        research_planner=planner,
        research_agent=research,
        financial_analyst_agent=analyst,
        research_coordinator=coordinator,
        report_agent=report_agent,
        verification_agent=verifier,
    )


def test_e2e_report_workflow_execution(mock_engine: FinovaOrchestrationEngine) -> None:
    """Test full multi-agent report generation workflow execution."""
    request = ReportGenerationRequest(
        question="Produce a comprehensive financial research brief on Apple Inc. for FY2023 covering margins, risks, and overview.",
        ticker="AAPL",
        reporting_period="FY2023",
        output_format="markdown",
    )

    response = mock_engine.run_report(request)

    assert isinstance(response, ReportGenerationResponse)
    assert response.status.lower() == "completed"
    assert response.report is not None
    assert response.report.ticker == "AAPL"
    assert response.total_sections >= 6
    assert response.markdown_content is not None
    assert "Financial Research Report: Apple Inc. (AAPL)" in response.markdown_content

    # Trace events should show nodes visited
    node_names = [e.node_name for e in response.trace]
    assert "research_planner" in node_names
    assert "research_agent" in node_names
    assert "financial_analyst_agent" in node_names
    assert "research_coordinator" in node_names
    assert "report_agent" in node_names
    assert "verification_agent" in node_names

    # Verify persistence in database
    saved = mock_engine.db.get_research_report(response.report_id)
    assert saved is not None
    assert saved["ticker"] == "AAPL"
    assert len(saved["sections"]) >= 6
    assert len(saved["references"]) >= 1
