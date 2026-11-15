"""Tests for execution event tracing and SQLite persistence."""

import pytest

from backend.agents.agent_models import AgentExecutionStatus
from backend.data.storage import Database
from backend.orchestration.execution_tracer import ExecutionTracer


def test_tracer_records_step_timing_and_output():
    db = Database(db_path=":memory:")
    tracer = ExecutionTracer(database=db)

    req_id = "test-req-123"
    db.save_workflow_run(
        {
            "request_id": req_id,
            "user_question": "Test question?",
            "status": "IN_PROGRESS",
        }
    )

    with tracer.trace_step(
        request_id=req_id,
        step_index=1,
        agent_name="TestAgent",
        node_name="test_node",
        input_summary="Test input",
    ) as step:
        step.set_output(
            summary="Test output summary",
            metadata={"items_count": 5},
            status=AgentExecutionStatus.SUCCESS.value,
        )

    events = db.list_execution_events(req_id)
    assert len(events) == 1
    ev = events[0]
    assert ev["request_id"] == req_id
    assert ev["step_index"] == 1
    assert ev["agent_name"] == "TestAgent"
    assert ev["node_name"] == "test_node"
    assert ev["duration_ms"] >= 0.0
    assert ev["output_summary"] == "Test output summary"
    assert ev["metadata"]["items_count"] == 5


def test_tracer_records_exceptions():
    db = Database(db_path=":memory:")
    tracer = ExecutionTracer(database=db)

    req_id = "test-req-err"
    db.save_workflow_run(
        {
            "request_id": req_id,
            "user_question": "Error question?",
            "status": "IN_PROGRESS",
        }
    )

    with pytest.raises(ValueError, match="Simulated agent failure"):
        with tracer.trace_step(
            request_id=req_id,
            step_index=2,
            agent_name="FailingAgent",
            node_name="failing_node",
        ):
            raise ValueError("Simulated agent failure")

    events = db.list_execution_events(req_id)
    assert len(events) == 1
    ev = events[0]
    assert ev["status"] == AgentExecutionStatus.FAILED.value
    assert "Simulated agent failure" in ev["error_message"]


def test_workflow_run_retrieval_with_events():
    db = Database(db_path=":memory:")
    req_id = "test-wf-full"

    db.save_workflow_run(
        {
            "request_id": req_id,
            "user_question": "What is AAPL gross margin?",
            "company_ticker": "AAPL",
            "intent": "FINANCIAL_ANALYSIS",
            "workflow_type": "financial_only",
            "status": "COMPLETED",
            "final_answer": "44.13% [C1]",
            "total_duration_ms": 125.5,
        }
    )

    db.save_execution_event(
        {
            "event_id": "ev-1",
            "request_id": req_id,
            "step_index": 1,
            "agent_name": "SupervisorAgent",
            "node_name": "supervisor",
            "status": "SUCCESS",
            "duration_ms": 10.2,
        }
    )
    db.save_execution_event(
        {
            "event_id": "ev-2",
            "request_id": req_id,
            "step_index": 2,
            "agent_name": "FinancialAnalystAgent",
            "node_name": "financial_analyst_agent",
            "status": "SUCCESS",
            "duration_ms": 80.5,
        }
    )

    wf = db.get_workflow_run(req_id)
    assert wf is not None
    assert wf["request_id"] == req_id
    assert wf["intent"] == "FINANCIAL_ANALYSIS"
    assert len(wf["trace_events"]) == 2
    assert wf["trace_events"][0]["step_index"] == 1
    assert wf["trace_events"][1]["step_index"] == 2
