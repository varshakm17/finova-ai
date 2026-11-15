"""Tests for strict verification routing enforcement in the LangGraph graph."""

from unittest.mock import MagicMock

from backend.agents.agent_models import AgentRunRequest, WorkflowStatus
from backend.data.storage import Database
from backend.orchestration.graph import FinovaOrchestrationEngine
from backend.verification.verification_models import OverallVerificationStatus


def test_rejected_verification_routes_to_safe_response():
    """Ensure that any answer failing claim-level verification is strictly withheld."""
    db = Database(db_path=":memory:")

    mock_rag = MagicMock()
    mock_rag.agent_name = "RAGAgent"
    mock_rag.execute.return_value = {
        "generated_answer": "Apple reported an ungrounded revenue of $999 Trillion [E1].",
        "current_step": "rag_agent",
    }

    mock_verifier = MagicMock()
    mock_verifier.agent_name = "VerificationAgent"
    mock_verifier.execute.return_value = {
        "verification_result": {
            "overall_status": OverallVerificationStatus.REJECTED.value,
            "is_valid": False,
            "warnings": [
                "Critical numerical contradiction detected on revenue figure."
            ],
        },
        "final_answer": None,
        "current_step": "verification_agent",
    }

    engine = FinovaOrchestrationEngine(
        database=db,
        rag_agent=mock_rag,
        verification_agent=mock_verifier,
    )

    req = AgentRunRequest(
        question="What is Apple's operational revenue in FY2023?",
        company_ticker="AAPL",
    )
    res = engine.run(req)

    # Must be marked REJECTED
    assert res.status == WorkflowStatus.REJECTED.value
    # Preliminary hallucinated answer must NOT be returned
    assert "$999 Trillion" not in res.final_answer
    assert "failed strict factual anti-hallucination verification" in res.final_answer
    # Trace must confirm execution through safe_response
    trace_nodes = [ev.node_name for ev in res.trace]
    assert "verification_agent" in trace_nodes
    assert "safe_response" in trace_nodes


def test_verified_answer_bypasses_safe_response():
    """Ensure that an audited, verified answer routes cleanly to completion."""
    db = Database(db_path=":memory:")

    mock_rag = MagicMock()
    mock_rag.agent_name = "RAGAgent"
    grounded_text = (
        "Apple recorded gross profit margin of 44.13% in fiscal year 2023 [C1]."
    )
    mock_rag.execute.return_value = {
        "generated_answer": grounded_text,
        "current_step": "rag_agent",
    }

    mock_verifier = MagicMock()
    mock_verifier.agent_name = "VerificationAgent"
    mock_verifier.execute.return_value = {
        "verification_result": {
            "overall_status": OverallVerificationStatus.VERIFIED.value,
            "is_valid": True,
            "warnings": [],
        },
        "final_answer": grounded_text,
        "current_step": "verification_agent",
    }

    engine = FinovaOrchestrationEngine(
        database=db,
        rag_agent=mock_rag,
        verification_agent=mock_verifier,
    )

    req = AgentRunRequest(
        question="What was Apple's gross profit margin in fiscal year 2023?",
        company_ticker="AAPL",
    )
    res = engine.run(req)

    assert res.status == WorkflowStatus.COMPLETED.value
    assert res.final_answer == grounded_text
    trace_nodes = [ev.node_name for ev in res.trace]
    assert "verification_agent" in trace_nodes
    assert "safe_response" not in trace_nodes


def test_verified_with_warnings_propagates_warnings():
    """Ensure answers verified with non-critical warnings propagate warnings while passing."""
    db = Database(db_path=":memory:")

    mock_rag = MagicMock()
    mock_rag.agent_name = "RAGAgent"
    grounded_text = "Apple strategy focused on services expansion [E1]."
    mock_rag.execute.return_value = {
        "generated_answer": grounded_text,
        "current_step": "rag_agent",
    }

    mock_verifier = MagicMock()
    mock_verifier.agent_name = "VerificationAgent"
    mock_verifier.execute.return_value = {
        "verification_result": {
            "overall_status": OverallVerificationStatus.VERIFIED_WITH_WARNINGS.value,
            "is_valid": True,
            "warnings": ["Minor citation formatting warning."],
        },
        "final_answer": grounded_text,
        "current_step": "verification_agent",
    }

    engine = FinovaOrchestrationEngine(
        database=db,
        rag_agent=mock_rag,
        verification_agent=mock_verifier,
    )

    req = AgentRunRequest(
        question="What was Apple's qualitative strategy in FY2023?",
        company_ticker="AAPL",
    )
    res = engine.run(req)

    assert res.status == WorkflowStatus.COMPLETED.value
    assert res.final_answer == grounded_text
    assert (
        res.verification_status
        == OverallVerificationStatus.VERIFIED_WITH_WARNINGS.value
    )
