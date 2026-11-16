"""Tests for Research Planner Agent (Session 11).

Validates autonomous multi-task research planning, task deconstruction,
target period extraction, filing section mapping, and plan validation.
"""

from __future__ import annotations

import pytest

from backend.agents.agent_models import (
    ResearchPlan,
    TaskType,
)
from backend.agents.research_planner import ResearchPlanner
from backend.agents.state import FinovaAgentState


@pytest.fixture
def planner() -> ResearchPlanner:
    return ResearchPlanner()


def test_planner_basic_objective_plan(planner: ResearchPlanner) -> None:
    """Test generating a structured plan for a comprehensive corporate brief."""
    plan = planner.create_plan(
        question="Provide a comprehensive financial research report on Apple covering gross margins, revenue growth, and primary risks.",
        ticker="AAPL",
        target_periods=["FY2022", "FY2023"],
    )

    assert isinstance(plan, ResearchPlan)
    assert plan.ticker == "AAPL"
    assert plan.is_valid is True
    assert len(plan.tasks) >= 4

    task_types = [t.task_type for t in plan.tasks]
    assert TaskType.FILING_RETRIEVAL in task_types
    assert TaskType.METRIC_CALCULATION in task_types
    assert TaskType.TREND_ANALYSIS in task_types
    assert TaskType.RISK_ANALYSIS in task_types


def test_planner_extracts_target_periods(planner: ResearchPlanner) -> None:
    """Test extracting periods from question string."""
    plan = planner.create_plan(
        question="Analyze Microsoft financial performance in FY2021, FY2022, and 2023.",
        ticker="MSFT",
    )

    assert "FY2021" in plan.target_periods or 2021 in plan.fiscal_years
    assert "FY2022" in plan.target_periods or 2022 in plan.fiscal_years
    assert "FY2023" in plan.target_periods or 2023 in plan.fiscal_years


def test_planner_identifies_required_metrics(planner: ResearchPlanner) -> None:
    """Test mapping query keywords to canonical XBRL calculation metrics."""
    plan = planner.create_plan(
        question="Evaluate Apple's liquidity, current ratio, operating margin, and free cash flow.",
        ticker="AAPL",
    )

    assert "current_ratio" in plan.required_metrics
    assert "operating_profit_margin" in plan.required_metrics
    assert "free_cash_flow" in plan.required_metrics


def test_planner_defines_expected_sections(planner: ResearchPlanner) -> None:
    """Test that all canonical report sections are specified in the plan."""
    plan = planner.create_plan(
        question="Full financial brief on NVDA.",
        ticker="NVDA",
    )

    section_keys = [s.section_key for s in plan.expected_sections]
    assert "executive_summary" in section_keys
    assert "financial_performance" in section_keys
    assert "historical_comparison" in section_keys
    assert "risk_factors" in section_keys
    assert any("source" in k or "reference" in k for k in section_keys)


def test_plan_validation_valid(planner: ResearchPlanner) -> None:
    """Test plan validation passes on properly constructed plan."""
    plan = planner.create_plan(
        question="Financial review of AAPL.",
        ticker="AAPL",
    )
    audit = planner.validate_plan(plan)
    assert audit.is_valid is True
    assert len(audit.issues) == 0


def test_plan_validation_missing_tasks(planner: ResearchPlanner) -> None:
    """Test plan validation fails if plan has no tasks."""
    plan = ResearchPlan(
        objective="Empty plan",
        ticker="AAPL",
        tasks=[],
    )
    audit = planner.validate_plan(plan)
    assert audit.is_valid is False
    assert any("task" in issue.lower() for issue in audit.issues)


def test_planner_execute_agent_node(planner: ResearchPlanner) -> None:
    """Test executing planner as a LangGraph node via FinovaAgentState."""
    state: FinovaAgentState = {
        "user_question": "Generate financial brief for Tesla FY2023.",
        "company_ticker": "TSLA",
        "reporting_period": "FY2023",
    }

    result = planner.execute(state)
    assert result["current_step"] == "research_planner"
    assert "research_plan" in result
    plan_dict = result["research_plan"]
    assert plan_dict["ticker"] == "TSLA"
    assert len(plan_dict["tasks"]) > 0
