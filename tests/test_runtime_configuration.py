"""Unit and integration tests for centralized configuration and security policies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.data.sec_client import (
    SECConfigurationError,
    is_placeholder_user_agent,
    mask_user_agent,
    validate_user_agent,
)
from backend.main import create_application
from config.settings import Settings


def test_configuration_validation_success() -> None:
    """Verify valid settings initialize with expected defaults."""
    settings = Settings(
        APP_NAME="Finova Test",
        PORT=8080,
        LOG_LEVEL="DEBUG",
    )
    assert settings.APP_NAME == "Finova Test"
    assert settings.PORT == 8080
    assert settings.LOG_LEVEL == "DEBUG"


def test_configuration_validation_invalid_port() -> None:
    """Verify invalid port raises validation error."""
    with pytest.raises(ValidationError):
        Settings(PORT=70000)

    with pytest.raises(ValidationError):
        Settings(PORT=-1)


def test_missing_sec_user_agent_rejection() -> None:
    """Verify empty or missing SEC User-Agent is rejected."""
    with pytest.raises(SECConfigurationError, match="SEC_USER_AGENT is not configured"):
        validate_user_agent("")

    with pytest.raises(SECConfigurationError, match="SEC_USER_AGENT is not configured"):
        validate_user_agent("   ")

    with pytest.raises(SECConfigurationError, match="SEC_USER_AGENT is not configured"):
        validate_user_agent(None)


def test_placeholder_sec_user_agent_rejection() -> None:
    """Verify placeholder contact emails are rejected when allow_placeholder=False."""
    placeholders = [
        "FinovaAI-Research/1.0 (contact@example.com)",
        "FinovaAI-Research/1.0 (admincontact@domain.com)",
        "FinovaAI-Research/1.0 (user@example.com)",
        "FinovaAI-Research/1.0 (tester@example.com)",
        "ResearchBot/1.0 (sample@samplecompany.com)",
    ]
    for p in placeholders:
        assert is_placeholder_user_agent(p) is True
        with pytest.raises(SECConfigurationError, match="placeholder"):
            validate_user_agent(p, allow_placeholder=False)


def test_valid_genuine_sec_user_agent_accepted() -> None:
    """Verify legitimate institutional or researcher contact is accepted."""
    genuine = "FinovaAI-Research/1.0 (researcher@fintech-institute.org)"
    assert is_placeholder_user_agent(genuine) is False
    validate_user_agent(genuine, allow_placeholder=False)


def test_sec_user_agent_masking() -> None:
    """Verify email address is masked for public display."""
    ua = "FinovaAI-Research/1.0 (jane.doe@university.edu)"
    masked = mask_user_agent(ua)
    assert "@" in masked
    assert "jane.doe" not in masked
    assert "j***@" in masked


def test_cors_development_policy() -> None:
    """Verify default CORS development policy allows local origins."""
    settings = Settings(
        APP_ENV="development",
        CORS_ORIGINS=["http://localhost:8501", "http://127.0.0.1:8501"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    assert "http://localhost:8501" in settings.get_cors_origins()
    assert settings.CORS_ALLOW_CREDENTIALS is True


def test_cors_origins_comma_separated_parsing() -> None:
    """Verify CORS origins string is parsed into list."""
    settings = Settings(
        CORS_ORIGINS="http://localhost:8501, http://backend:8000, https://app.finova.io",
    )
    origins = settings.get_cors_origins()
    assert len(origins) == 3
    assert "https://app.finova.io" in origins


def test_wildcard_cors_with_credentials_rejected() -> None:
    """Verify wildcard CORS '*' with credentials is automatically restricted."""
    settings = Settings(
        CORS_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS=True,
    )
    # The application factory enforces allow_credentials=False when '*' is present
    app = create_application(custom_settings=settings)
    cors_mw = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors_mw) == 1
    assert cors_mw[0].kwargs.get("allow_credentials") is False


def test_production_readiness_warnings() -> None:
    """Verify production readiness audit catches insecure configurations."""
    prod_insecure = Settings(
        APP_ENV="production",
        DEBUG=True,
        CORS_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS=True,
        SEC_USER_AGENT="Finova/1.0 (contact@example.com)",
    )
    warnings = prod_insecure.validate_production_readiness()
    assert len(warnings) >= 2
    warn_text = " ".join(warnings)
    assert "DEBUG" in warn_text
    assert "CORS" in warn_text or "placeholder" in warn_text
