"""Tests for Extended Health and Runtime Diagnostics Endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Fixture providing TestClient for FastAPI."""
    with TestClient(app) as test_client:
        yield test_client


def test_api_v1_health_diagnostics_structure(client: TestClient) -> None:
    """Verify that /api/v1/health returns rich subsystem diagnostics and masked configuration."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "Finova AI"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data
    assert data["uptime_seconds"] >= 0.0

    subsystems = data.get("subsystems", {})
    assert "database" in subsystems
    assert "sec_client" in subsystems
    assert "retrieval_index" in subsystems
    assert "llm_provider" in subsystems
    assert "verification_service" in subsystems

    # Check database subsystem details
    db = subsystems["database"]
    assert db["status"] in ("Healthy", "Degraded", "Unavailable")
    assert db["driver"] == "sqlite3"
    assert "tables_count" in db

    # Check SEC client subsystem details
    sec = subsystems["sec_client"]
    assert sec["status"] in ("Healthy", "Degraded")
    assert sec["user_agent_valid"] is True
    assert sec["fair_access_rps"] == 8.0

    # Check config masking (no credentials or tokens leaked)
    cfg = data.get("config", {})
    assert "APP_NAME" in cfg
    assert "DATABASE_URL" in cfg
    assert "token" not in "".join(cfg.keys()).lower()
    assert "password" not in "".join(cfg.keys()).lower()
    assert "secret" not in "".join(cfg.keys()).lower()


def test_api_v1_health_subsystem_reporting(client: TestClient) -> None:
    """Verify that retrieval index and verification engine details are reported."""
    response = client.get("/api/v1/health")
    data = response.json()
    subsystems = data["subsystems"]

    retrieval = subsystems["retrieval_index"]
    assert "dense_faiss" in retrieval
    assert "sparse_bm25" in retrieval
    assert "cross_encoder_reranker" in retrieval

    verification = subsystems["verification_service"]
    assert "numeric_tolerance_pct" in verification
    assert "max_regeneration_attempts" in verification
