"""API integration tests for Multi-Agent Orchestration endpoints."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_api_agents_run_unsupported_query():
    response = client.post(
        "/api/v1/agents/run",
        json={"question": "Should I buy Tesla stock today?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "UNSUPPORTED_OR_AMBIGUOUS"
    assert data["workflow_type"] == "safe_rejection"
    assert data["status"] == "REJECTED"
    assert "regulatory SEC financial research assistant" in data["final_answer"]
    assert len(data["trace"]) >= 2


def test_api_agents_run_with_mock_response():
    response = client.post(
        "/api/v1/agents/run",
        json={
            "question": "What are Apple's main operational challenges?",
            "company_ticker": "AAPL",
            "mock_llm_response": "The available SEC filing disclosures do not provide sufficient evidence to answer this question.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "GENERAL_RESEARCH"
    assert data["workflow_type"] == "research_only"
    assert "sufficient evidence" in data["final_answer"]


def test_api_agents_run_validation_error():
    # Question too short
    response = client.post(
        "/api/v1/agents/run",
        json={"question": "ab"},
    )
    assert response.status_code == 422


def test_api_get_workflow_by_id_and_list():
    # Run a workflow first
    run_resp = client.post(
        "/api/v1/agents/run",
        json={"question": "What is Apple's business model?"},
    )
    assert run_resp.status_code == 200
    req_id = run_resp.json()["request_id"]

    # Fetch by request_id
    get_resp = client.get(f"/api/v1/agents/workflows/{req_id}")
    assert get_resp.status_code == 200
    wf_data = get_resp.json()
    assert wf_data["request_id"] == req_id
    assert len(wf_data["trace_events"]) >= 1

    # Fetch list
    list_resp = client.get("/api/v1/agents/workflows?limit=10")
    assert list_resp.status_code == 200
    wfs = list_resp.json()
    assert isinstance(wfs, list)
    assert any(w["request_id"] == req_id for w in wfs)


def test_api_get_workflow_not_found():
    response = client.get("/api/v1/agents/workflows/non-existent-uuid-999")
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()
