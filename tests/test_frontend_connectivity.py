"""Unit tests for Frontend Backend Client & URL Resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from config.settings import Settings
from frontend.backend_client import (
    BackendEndpoints,
    check_backend_health,
    resolve_backend_endpoints,
)


def test_resolve_local_backend_url() -> None:
    """Verify local development URL resolution."""
    settings = Settings(HOST="127.0.0.1", PORT=8000, API_V1_PREFIX="/api/v1")
    endpoints = resolve_backend_endpoints(settings=settings)

    assert endpoints.base_url == "http://127.0.0.1:8000"
    assert endpoints.api_v1_url == "http://127.0.0.1:8000/api/v1"
    assert endpoints.health_url == "http://127.0.0.1:8000/api/v1/health"
    assert endpoints.root_health_url == "http://127.0.0.1:8000/health"


def test_resolve_docker_backend_url() -> None:
    """Verify Docker service-name URL resolution avoids duplicate /api/v1."""
    # When BACKEND_API_URL is supplied with /api/v1
    endpoints = resolve_backend_endpoints(custom_url="http://backend:8000/api/v1")

    assert endpoints.base_url == "http://backend:8000"
    assert endpoints.api_v1_url == "http://backend:8000/api/v1"
    assert endpoints.health_url == "http://backend:8000/api/v1/health"
    assert (
        endpoints.endpoint("/reports/generate")
        == "http://backend:8000/api/v1/reports/generate"
    )
    assert (
        endpoints.endpoint("/api/v1/reports/generate")
        == "http://backend:8000/api/v1/reports/generate"
    )


def test_resolve_custom_backend_url() -> None:
    """Verify remote or custom protocol URL resolution."""
    endpoints = resolve_backend_endpoints(
        custom_url="https://finova.corp.internal:8443"
    )

    assert endpoints.base_url == "https://finova.corp.internal:8443"
    assert endpoints.api_v1_url == "https://finova.corp.internal:8443/api/v1"
    assert endpoints.health_url == "https://finova.corp.internal:8443/api/v1/health"


def test_trailing_slash_normalization() -> None:
    """Verify trailing slashes are cleanly stripped without corruption."""
    endpoints = resolve_backend_endpoints(custom_url="http://backend:8000/api/v1///")

    assert endpoints.base_url == "http://backend:8000"
    assert endpoints.api_v1_url == "http://backend:8000/api/v1"
    assert not endpoints.api_v1_url.endswith("/")


def test_incorrect_url_configuration() -> None:
    """Verify invalid URL without valid hostname raises ValueError."""
    with pytest.raises(ValueError, match="Invalid backend URL"):
        resolve_backend_endpoints(custom_url="http://")

    with pytest.raises(ValueError, match="Invalid backend URL"):
        resolve_backend_endpoints(custom_url="://missing-scheme")

    # Invalid schemes
    with pytest.raises(ValueError, match="scheme"):
        resolve_backend_endpoints(custom_url="ftp://backend:8000")

    with pytest.raises(ValueError, match="scheme"):
        resolve_backend_endpoints(custom_url="ws://backend:8000")

    # Invalid port numbers
    with pytest.raises(ValueError, match="port"):
        resolve_backend_endpoints(custom_url="http://backend:99999")

    with pytest.raises(ValueError, match="port"):
        resolve_backend_endpoints(custom_url="http://backend:0")


def test_url_resolver_edge_cases() -> None:
    """Verify URL resolver handles empty env vars, query params, fragments, and IPv4 addresses."""
    # Empty string in custom_url falls back to defaults
    endpoints_empty = resolve_backend_endpoints(custom_url="   ")
    assert "127.0.0.1" in endpoints_empty.base_url

    # IPv4 address
    endpoints_ip = resolve_backend_endpoints(custom_url="http://192.168.1.100:8000")
    assert endpoints_ip.base_url == "http://192.168.1.100:8000"
    assert endpoints_ip.api_v1_url == "http://192.168.1.100:8000/api/v1"

    # URL with query parameters and fragments
    endpoints_query = resolve_backend_endpoints(
        custom_url="http://backend:8000/api/v1?env=prod&debug=false#top"
    )
    assert endpoints_query.base_url == "http://backend:8000"
    assert endpoints_query.api_v1_url == "http://backend:8000/api/v1"

    # endpoint path segment resolution without duplication
    assert endpoints_ip.endpoint("health") == "http://192.168.1.100:8000/api/v1/health"
    assert endpoints_ip.endpoint("/health") == "http://192.168.1.100:8000/api/v1/health"
    assert (
        endpoints_ip.endpoint("api/v1/health")
        == "http://192.168.1.100:8000/api/v1/health"
    )
    assert (
        endpoints_ip.endpoint("/api/v1/health")
        == "http://192.168.1.100:8000/api/v1/health"
    )
    assert endpoints_ip.endpoint("") == "http://192.168.1.100:8000/api/v1"
    assert endpoints_ip.endpoint("api/v1") == "http://192.168.1.100:8000/api/v1"

    # root_endpoint helper
    assert endpoints_ip.root_endpoint("health") == "http://192.168.1.100:8000/health"
    assert endpoints_ip.root_endpoint("/health") == "http://192.168.1.100:8000/health"
    assert endpoints_ip.root_endpoint("") == "http://192.168.1.100:8000"


def test_check_backend_health_success() -> None:
    """Verify successful health response parsing."""
    endpoints = BackendEndpoints(
        base_url="http://testserver",
        api_v1_url="http://testserver/api/v1",
        health_url="http://testserver/api/v1/health",
        root_health_url="http://testserver/health",
        configured_from="test",
    )
    mock_payload = {
        "status": "healthy",
        "app_name": "Finova AI",
        "subsystems": {"database": {"status": "Healthy"}},
    }

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        is_online, data, err = check_backend_health(endpoints)
        assert is_online is True
        assert data is not None
        assert data["status"] == "healthy"
        assert err is None


def test_check_backend_health_timeout() -> None:
    """Verify graceful handling when backend connection times out."""
    endpoints = BackendEndpoints(
        base_url="http://unreachable:8000",
        api_v1_url="http://unreachable:8000/api/v1",
        health_url="http://unreachable:8000/api/v1/health",
        root_health_url="http://unreachable:8000/health",
        configured_from="test",
    )

    with patch.object(httpx.Client, "get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timed out")

        is_online, data, err = check_backend_health(endpoints, timeout=0.1)
        assert is_online is False
        assert data is None
        assert "timed out" in err.lower()


def test_check_backend_health_unavailable() -> None:
    """Verify handling when backend returns HTTP 503 unavailable."""
    endpoints = BackendEndpoints(
        base_url="http://degraded:8000",
        api_v1_url="http://degraded:8000/api/v1",
        health_url="http://degraded:8000/api/v1/health",
        root_health_url="http://degraded:8000/health",
        configured_from="test",
    )

    with patch.object(httpx.Client, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Degraded"
        mock_resp.json.return_value = {"status": "unavailable"}
        mock_get.return_value = mock_resp

        is_online, data, err = check_backend_health(endpoints)
        assert is_online is False
        assert "503" in err
