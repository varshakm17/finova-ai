"""Automated tests for FastAPI application health check and core foundation."""

import pytest
from fastapi.testclient import TestClient

from backend.main import app, create_application
from backend.utils.logger import get_logger, setup_logging
from config.settings import Settings, get_settings


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Fixture providing a TestClient for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


def test_app_initialization() -> None:
    """Verify that the FastAPI application initializes with correct metadata."""
    test_app = create_application()
    assert test_app.title == "Finova AI"
    assert test_app.version == "0.1.0"
    assert "financial research and intelligence" in test_app.description.lower()


def test_health_endpoint_status_code(client: TestClient) -> None:
    """Verify that GET /health responds with HTTP 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_payload(client: TestClient) -> None:
    """Verify that GET /health returns expected operational status and version."""
    response = client.get("/health")
    data = response.json()

    assert data["status"] == "healthy"
    assert data["app_name"] == "Finova AI"
    assert data["version"] == "0.1.0"
    assert "environment" in data


def test_versioned_api_health_endpoint(client: TestClient) -> None:
    """Verify that GET /api/v1/health functions identically through the API router."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "Finova AI"
    assert data["version"] == "0.1.0"


def test_root_endpoint_metadata(client: TestClient) -> None:
    """Verify that the root endpoint returns system identity and docs link."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Finova AI"
    assert data["version"] == "0.1.0"
    assert data["status"] == "operational"
    assert data["documentation"] == "/docs"


def test_settings_defaults() -> None:
    """Verify that configuration settings load expected defaults without errors."""
    settings = get_settings()
    assert settings.APP_NAME == "Finova AI"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.HOST == "127.0.0.1"
    assert settings.PORT == 8000
    assert "sqlite" in settings.DATABASE_URL
    assert isinstance(settings.DEBUG, bool)


def test_custom_settings_instantiation() -> None:
    """Verify that Settings can be instantiated with custom values without a .env file."""
    custom = Settings(
        APP_NAME="Finova Custom",
        APP_ENV="test",
        DEBUG=False,
        LOG_LEVEL="DEBUG",
    )
    assert custom.APP_NAME == "Finova Custom"
    assert custom.APP_ENV == "test"
    assert custom.DEBUG is False
    assert custom.LOG_LEVEL == "DEBUG"


def test_logging_setup() -> None:
    """Verify that the centralized logging system initializes without exceptions."""
    logger = setup_logging(log_level="INFO", log_file_path="logs/test_run.log")
    assert logger is not None

    component_logger = get_logger("unit_test")
    assert component_logger.name == "finova.unit_test"
