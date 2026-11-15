"""Tests for LangGraph orchestration graph topologies and routing."""

from unittest.mock import MagicMock

from backend.agents.agent_models import (
    AgentIntent,
    AgentRunRequest,
    AgentWorkflowType,
    WorkflowStatus,
)
from backend.data.storage import Database
from backend.orchestration.graph import (
    FinovaOrchestrationEngine,
    create_finova_workflow,
)
from backend.orchestration.workflow_config import WorkflowConfig
from backend.verification.verification_models import (
    OverallVerificationStatus,
)


def get_test_engine(db_path: str = ":memory:"):
    db = Database(db_path=db_path)

    # Mock RAG agent with deterministic response
    mock_rag = MagicMock()
    mock_rag.agent_name = "RAGAgent"
    mock_rag.execute.side_effect = lambda state: {
        "generated_answer": "According to disclosures, gross profit was consistent with guidance [E1].",
        "current_step": "rag_agent",
    }

    # Mock Verification agent with verified status
    mock_verifier = MagicMock()
    mock_verifier.agent_name = "VerificationAgent"
    mock_verifier.execute.side_effect = lambda state: {
        "verification_result": {
            "overall_status": OverallVerificationStatus.VERIFIED.value,
            "is_valid": True,
            "warnings": [],
        },
        "final_answer": state.get("generated_answer"),
        "current_step": "verification_agent",
    }

    engine = FinovaOrchestrationEngine(
        config=WorkflowConfig(max_steps=10),
        database=db,
        rag_agent=mock_rag,
        verification_agent=mock_verifier,
    )
    return engine


def test_create_finova_workflow_factory():
    graph = create_finova_workflow()
    assert "supervisor" in graph.nodes
    assert "research_agent" in graph.nodes
    assert "financial_analyst_agent" in graph.nodes
    assert "rag_agent" in graph.nodes
    assert "verification_agent" in graph.nodes
    assert "safe_response" in graph.nodes


def test_graph_general_research_routing():
    engine = get_test_engine()
    req = AgentRunRequest(
        question="What are Apple's primary business and operational risk factors in MD&A?",
        company_ticker="AAPL",
    )
    res = engine.run(req)
    assert res.intent == AgentIntent.GENERAL_RESEARCH.value
    assert res.workflow_type == AgentWorkflowType.RESEARCH_ONLY.value
    assert res.status == WorkflowStatus.COMPLETED.value
    node_names = [ev.node_name for ev in res.trace]
    assert "supervisor" in node_names
    assert "research_agent" in node_names
    assert "merge_evidence" in node_names
    assert "rag_agent" in node_names
    assert "verification_agent" in node_names


def test_graph_financial_analysis_routing():
    engine = get_test_engine()
    req = AgentRunRequest(
        question="What is the gross margin and net profit margin for Apple?",
        company_ticker="AAPL",
    )
    res = engine.run(req)
    assert res.intent == AgentIntent.FINANCIAL_ANALYSIS.value
    assert res.workflow_type == AgentWorkflowType.FINANCIAL_ONLY.value
    assert res.status == WorkflowStatus.COMPLETED.value
    node_names = [ev.node_name for ev in res.trace]
    assert "supervisor" in node_names
    assert "financial_analyst_agent" in node_names
    assert "merge_evidence" in node_names
    assert "rag_agent" in node_names
    assert "verification_agent" in node_names


def test_graph_combined_analysis_routing():
    engine = get_test_engine()
    req = AgentRunRequest(
        question="Explain Apple's business strategy and its operating margin in FY2023.",
        company_ticker="AAPL",
        reporting_period="FY2023",
    )
    res = engine.run(req)
    assert res.intent == AgentIntent.COMBINED_ANALYSIS.value
    assert res.workflow_type == AgentWorkflowType.COMBINED_ANALYSIS.value
    node_names = [ev.node_name for ev in res.trace]
    assert "supervisor" in node_names
    assert "research_agent" in node_names
    assert "financial_analyst_agent" in node_names
    assert "merge_evidence" in node_names
    assert "rag_agent" in node_names
    assert "verification_agent" in node_names


def test_graph_comparative_research_routing():
    engine = get_test_engine()
    req = AgentRunRequest(
        question="Compare Apple and Microsoft in operating margins and competitive strategy.",
    )
    res = engine.run(req)
    assert res.intent == AgentIntent.COMPARATIVE_RESEARCH.value
    assert res.workflow_type == AgentWorkflowType.COMPARATIVE_ANALYSIS.value
    node_names = [ev.node_name for ev in res.trace]
    assert "supervisor" in node_names
    assert "research_agent" in node_names
    assert "financial_analyst_agent" in node_names


def test_graph_unsupported_rejection_routing():
    engine = get_test_engine()
    req = AgentRunRequest(
        question="Should I buy Tesla stock before market close tomorrow?",
    )
    res = engine.run(req)
    assert res.intent == AgentIntent.UNSUPPORTED_OR_AMBIGUOUS.value
    assert res.workflow_type == AgentWorkflowType.SAFE_REJECTION.value
    assert res.status == WorkflowStatus.REJECTED.value
    assert "regulatory SEC financial research assistant" in res.final_answer
    node_names = [ev.node_name for ev in res.trace]
    assert "supervisor" in node_names
    assert "safe_response" in node_names
    assert "rag_agent" not in node_names
