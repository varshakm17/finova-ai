"""Tests for Supervisor Agent intent classification and routing."""

from backend.agents.agent_models import AgentIntent, AgentWorkflowType
from backend.agents.state import FinovaAgentState
from backend.agents.supervisor import SupervisorAgent


def test_supervisor_initialization():
    supervisor = SupervisorAgent()
    assert supervisor.agent_name == "SupervisorAgent"
    assert "Supervisor" in supervisor.description


def test_supervisor_classifies_general_research():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "What are the primary operational risk factors for Apple described in the MD&A section?",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.GENERAL_RESEARCH.value
    assert res["workflow_type"] == AgentWorkflowType.RESEARCH_ONLY.value
    assert "research_agent" in res["selected_agents"]
    assert res["company_ticker"] == "AAPL"


def test_supervisor_classifies_financial_analysis():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "What is the net profit margin and debt-to-equity ratio for MSFT?",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.FINANCIAL_ANALYSIS.value
    assert res["workflow_type"] == AgentWorkflowType.FINANCIAL_ONLY.value
    assert "financial_analyst_agent" in res["selected_agents"]
    assert res["company_ticker"] == "MSFT"


def test_supervisor_classifies_combined_analysis():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "Analyze Apple's business strategy and explain its gross profit margin trend in FY2023.",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.COMBINED_ANALYSIS.value
    assert res["workflow_type"] == AgentWorkflowType.COMBINED_ANALYSIS.value
    assert "research_agent" in res["selected_agents"]
    assert "financial_analyst_agent" in res["selected_agents"]
    assert res["company_ticker"] == "AAPL"
    assert res["reporting_period"] == "FY2023"


def test_supervisor_classifies_comparative_research():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "Compare the operating margins and competitive strategy between Apple and Microsoft.",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.COMPARATIVE_RESEARCH.value
    assert res["workflow_type"] == AgentWorkflowType.COMPARATIVE_ANALYSIS.value
    assert "research_agent" in res["selected_agents"]
    assert "financial_analyst_agent" in res["selected_agents"]


def test_supervisor_rejects_stock_trading_advice():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "Should I buy Tesla stock before earnings or sell?",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.UNSUPPORTED_OR_AMBIGUOUS.value
    assert res["workflow_type"] == AgentWorkflowType.SAFE_REJECTION.value
    assert "safe_response" in res["selected_agents"]


def test_supervisor_rejects_ambiguous_short_question():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "hello there",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["intent"] == AgentIntent.UNSUPPORTED_OR_AMBIGUOUS.value
    assert res["workflow_type"] == AgentWorkflowType.SAFE_REJECTION.value


def test_supervisor_preserves_explicit_ticker_and_period():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "Analyze revenue trends and gross margin.",
        "company_ticker": "NVDA",
        "reporting_period": "2024",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert res["company_ticker"] == "NVDA"
    assert res["reporting_period"] == "2024"
    assert res["intent"] == AgentIntent.FINANCIAL_ANALYSIS.value


def test_supervisor_records_routing_reason_metadata():
    supervisor = SupervisorAgent()
    state: FinovaAgentState = {
        "user_question": "What are Apple business risks?",
        "step_count": 0,
    }
    res = supervisor.execute(state)
    assert "metadata" in res
    assert "routing_reason" in res["metadata"]
    assert len(res["metadata"]["routing_reason"]) > 0
