"""Tests for Report Generation Agent (Session 11).

Validates multi-section report assembly, markdown formatting, HTML rendering,
comparative table generation, and citation attribution.
"""

from __future__ import annotations

import pytest

from backend.agents.agent_models import FinancialResearchReport, ReportTable
from backend.agents.report_agent import ReportAgent
from backend.agents.state import FinovaAgentState


@pytest.fixture
def report_agent() -> ReportAgent:
    return ReportAgent()


def test_build_financial_ratios_table(report_agent: ReportAgent) -> None:
    """Test generating a structured table from calculation receipts."""
    calc_map = {
        "C1": {
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "fiscal_year": 2023,
            "formula_expression": "(gross_profit / revenue) * 100",
        },
        "C2": {
            "metric_name": "current_ratio",
            "calculated_value": 0.988,
            "unit": "ratio",
            "fiscal_year": 2023,
            "formula_expression": "current_assets / current_liabilities",
        },
    }

    table = report_agent.build_financial_ratios_table(calc_map)
    assert isinstance(table, ReportTable)
    assert len(table.rows) == 2
    assert "Metric" in table.headers
    assert "Calculated Value" in table.headers

    # Check Markdown rendering
    md = report_agent.format_markdown_table(table)
    assert "| Gross Profit Margin |" in md
    assert "44.13%" in md
    assert "[C1]" in md


def test_build_historical_comparison_table(report_agent: ReportAgent) -> None:
    """Test comparative multi-period table formatting."""
    comparisons = [
        {
            "metric_name": "gross_profit_margin",
            "base_period": "FY2022",
            "comparison_period": "FY2023",
            "base_value": 43.31,
            "comparison_value": 44.13,
            "unit": "percentage",
            "absolute_delta": 0.82,
            "percentage_delta": 1.89,
        }
    ]
    trends = [
        {
            "metric_name": "gross_profit_margin",
            "direction": "UPWARD",
            "interpretation_notes": "Profitability margins expanded.",
        }
    ]

    table = report_agent.build_historical_comparison_table(comparisons, trends)
    assert len(table.rows) == 1
    md = report_agent.format_markdown_table(table)
    assert "FY2022" in md
    assert "FY2023" in md
    assert "+0.82%" in md
    assert "+1.9%" in md


def test_render_html_output(report_agent: ReportAgent) -> None:
    """Test rendering publication-quality semantic HTML report."""
    sections = report_agent.assemble_sections(
        company_name="Apple Inc.",
        ticker="AAPL",
        period="FY2023",
        question="Analyze financial performance",
        section_findings={
            "executive_summary": ["Operational performance remained strong."],
            "company_overview": ["Apple manufactures consumer electronics."],
        },
        evidence_map={
            "E1": {"section_identifier": "ITEM_1", "text": "Apple is a tech company."}
        },
        calc_map={
            "C1": {
                "metric_name": "gross_profit_margin",
                "calculated_value": 44.13,
                "unit": "percentage",
                "fiscal_year": 2023,
            }
        },
        trends=[],
        comparisons=[],
    )
    references = report_agent.build_references(
        evidence_map={
            "E1": {"section_identifier": "ITEM_1", "text": "Apple is a tech company."}
        },
        calc_map={
            "C1": {
                "metric_name": "gross_profit_margin",
                "calculated_value": 44.13,
                "unit": "percentage",
                "fiscal_year": 2023,
            }
        },
    )

    html_out = report_agent.render_html(
        company_name="Apple Inc.",
        ticker="AAPL",
        period="FY2023",
        sections=sections,
        references=references,
        verification_status="VERIFIED",
    )

    assert "<!DOCTYPE html>" in html_out
    assert "<title>Financial Research Brief - Apple Inc. (AAPL)</title>" in html_out
    assert "class='badge badge-status'" in html_out
    assert "Executive Summary" in html_out
    assert "Apple Inc." in html_out


def test_report_agent_execute(report_agent: ReportAgent) -> None:
    """Test complete ReportAgent execution node producing valid report dictionary."""
    state: FinovaAgentState = {
        "user_question": "Full research brief on Microsoft",
        "company_ticker": "MSFT",
        "reporting_period": "FY2023",
        "consolidated_findings": {
            "evidence_map": {
                "E1": {
                    "citation_id": "E1",
                    "chunk_id": "c1",
                    "section_identifier": "ITEM_7",
                    "text": "Commercial cloud revenue increased 22%.",
                    "company_name": "Microsoft Corp",
                    "ticker": "MSFT",
                }
            },
            "calculation_map": {
                "C1": {
                    "citation_id": "C1",
                    "calculation_id": "r1",
                    "metric_name": "operating_profit_margin",
                    "calculated_value": 41.77,
                    "unit": "percentage",
                    "fiscal_year": 2023,
                }
            },
            "section_findings": {
                "executive_summary": ["Microsoft achieved solid cloud growth."],
            },
            "trends": [],
            "comparisons": [],
        },
        "warnings": [],
    }

    result = report_agent.execute(state)
    assert result["current_step"] == "report_agent"
    assert "generated_report" in result
    assert "report_markdown" in result
    assert "report_html" in result

    rep = FinancialResearchReport.model_validate(result["generated_report"])
    assert rep.company_name == "Microsoft Corp"
    assert rep.ticker == "MSFT"
    assert len(rep.sections) >= 6
    assert len(rep.references) == 2
