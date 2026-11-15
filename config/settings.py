"""Application configuration management using Pydantic Settings.

Loads configuration from environment variables and an optional .env file.
Provides safe defaults for all fields so that missing optional configuration
never prevents the application from starting.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Central application settings for Finova AI."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core Application Metadata
    APP_NAME: str = Field(
        default="Finova AI",
        description="Public display name of the application",
    )
    APP_ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Runtime environment identifier",
    )
    DEBUG: bool = Field(
        default=True,
        description="Enable debug mode and verbose output",
    )
    APP_VERSION: str = Field(
        default="0.1.0",
        description="Semantic application version",
    )

    # Server Configuration
    HOST: str = Field(
        default="127.0.0.1",
        description="Backend host IP binding",
    )
    PORT: int = Field(
        default=8000,
        description="Backend port binding",
    )
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="Prefix for version 1 API routes",
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging severity threshold (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    LOG_FILE_PATH: str = Field(
        default="logs/finova.log",
        description="Path relative to project root for application log output",
    )

    # Database Configuration
    DATABASE_URL: str = Field(
        default="sqlite:///./finova.db",
        description="Database connection string (SQLite file path for initial local setup)",
    )

    # SEC EDGAR Integration Placeholder
    SEC_USER_AGENT: str = Field(
        default="FinovaAI-Research/0.1.0 (contact@example.com)",
        description=(
            "SEC EDGAR User-Agent header in the format: 'ApplicationName AdminContact@domain.com'. "
            "A valid email and identifier must be configured before making requests to SEC EDGAR."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance.

    Returns:
        Settings: Initialized settings populated from environment and defaults.
    """
    return Settings()
