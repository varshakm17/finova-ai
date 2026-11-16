"""Tests for Deterministic Multi-Period Trend Calculations (Session 11).

Validates calculation of directional trends, percentage changes,
absolute deltas, and semantic interpretation notes. Guaranteed zero LLM arithmetic.
"""

from __future__ import annotations

import pytest

from backend.agents.financial_analyst_agent import FinancialAnalystAgent


@pytest.fixture
def analyst_agent() -> FinancialAnalystAgent:
    return FinancialAnalystAgent()


def test_compute_trends_upward_margin(analyst_agent: FinancialAnalystAgent) -> None:
    """Test upward trend calculation for profitability margin."""
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "gross_profit_margin",
            "calculated_value": 43.31,
            "unit": "percentage",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "status": "calculated",
        },
        {
            "calculation_id": "c2",
            "metric_name": "gross_profit_margin",
            "calculated_value": 44.13,
            "unit": "percentage",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "status": "calculated",
        },
    ]

    trends, comparisons = analyst_agent.compute_trends(receipts)

    assert len(trends) == 1
    t = trends[0]
    assert t.metric_name == "gross_profit_margin"
    assert t.direction == "UPWARD"
    assert t.absolute_change == pytest.approx(0.82, rel=1e-3)
    # (44.13 - 43.31) / 43.31 * 100 = 1.89%
    assert t.percentage_change == pytest.approx(1.89, rel=1e-2)
    assert "expanded" in t.interpretation_notes.lower()

    assert len(comparisons) == 1
    comp = comparisons[0]
    assert comp.base_period == "FY2022"
    assert comp.comparison_period == "FY2023"
    assert comp.absolute_delta == pytest.approx(0.82, rel=1e-3)


def test_compute_trends_downward_leverage(analyst_agent: FinancialAnalystAgent) -> None:
    """Test downward trend in leverage indicates deleveraging."""
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "debt_to_equity_ratio",
            "calculated_value": 2.50,
            "unit": "ratio",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "status": "calculated",
        },
        {
            "calculation_id": "c2",
            "metric_name": "debt_to_equity_ratio",
            "calculated_value": 1.80,
            "unit": "ratio",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "status": "calculated",
        },
    ]

    trends, comparisons = analyst_agent.compute_trends(receipts)

    assert len(trends) == 1
    t = trends[0]
    assert t.direction == "DOWNWARD"
    assert t.absolute_change == pytest.approx(-0.70, rel=1e-3)
    # (1.80 - 2.50) / 2.50 * 100 = -28.0%
    assert t.percentage_change == pytest.approx(-28.0, rel=1e-2)
    assert (
        "de-leveraging" in t.interpretation_notes.lower()
        or "decreased" in t.interpretation_notes.lower()
    )


def test_compute_trends_flat_trajectory(analyst_agent: FinancialAnalystAgent) -> None:
    """Test flat trend when values remain within tolerance."""
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "current_ratio",
            "calculated_value": 1.05,
            "unit": "ratio",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "status": "calculated",
        },
        {
            "calculation_id": "c2",
            "metric_name": "current_ratio",
            "calculated_value": 1.05,
            "unit": "ratio",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "status": "calculated",
        },
    ]

    trends, _ = analyst_agent.compute_trends(receipts)
    assert len(trends) == 1
    assert trends[0].direction == "FLAT"
    assert trends[0].absolute_change == 0.0


def test_compute_trends_multi_year_three_periods(
    analyst_agent: FinancialAnalystAgent,
) -> None:
    """Test longitudinal analysis across 3 fiscal years."""
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "operating_profit_margin",
            "calculated_value": 29.78,
            "unit": "percentage",
            "fiscal_year": 2021,
            "fiscal_period": "FY",
            "status": "calculated",
        },
        {
            "calculation_id": "c2",
            "metric_name": "operating_profit_margin",
            "calculated_value": 30.29,
            "unit": "percentage",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "status": "calculated",
        },
        {
            "calculation_id": "c3",
            "metric_name": "operating_profit_margin",
            "calculated_value": 29.82,
            "unit": "percentage",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "status": "calculated",
        },
    ]

    trends, comparisons = analyst_agent.compute_trends(receipts)

    assert len(trends) == 1
    # 2021 -> 2022 is UP, 2022 -> 2023 is DOWN -> direction is MIXED
    assert trends[0].direction == "MIXED"
    assert len(comparisons) == 2
    assert comparisons[0].base_period == "FY2021"
    assert comparisons[0].comparison_period == "FY2022"
    assert comparisons[1].base_period == "FY2022"
    assert comparisons[1].comparison_period == "FY2023"


def test_compute_trends_filters_uncalculated(
    analyst_agent: FinancialAnalystAgent,
) -> None:
    """Test that unavailable or invalid calculation receipts are ignored."""
    receipts = [
        {
            "calculation_id": "c1",
            "metric_name": "revenue_growth",
            "calculated_value": None,
            "unit": "percentage",
            "fiscal_year": 2022,
            "status": "unavailable",
        },
        {
            "calculation_id": "c2",
            "metric_name": "revenue_growth",
            "calculated_value": 5.4,
            "unit": "percentage",
            "fiscal_year": 2023,
            "status": "calculated",
        },
    ]

    trends, comparisons = analyst_agent.compute_trends(receipts)
    # Only 1 calculated value, so no trend or comparison can be formed
    assert len(trends) == 0
    assert len(comparisons) == 0
