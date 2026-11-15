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

    # SEC Filing Document Ingestion & Chunking (Session 03)
    FILINGS_STORAGE_DIR: str = Field(
        default="datasets/filings",
        description="Local directory for storing downloaded raw SEC filing HTML documents",
    )
    MAX_DOCUMENT_SIZE_BYTES: int = Field(
        default=25 * 1024 * 1024,
        description="Maximum permitted download size for SEC filing documents (bytes)",
    )
    CHUNK_TARGET_SIZE: int = Field(
        default=3500,
        description="Target text chunk character size for section-aware chunking",
    )
    CHUNK_OVERLAP: int = Field(
        default=400,
        description="Character overlap between consecutive chunks",
    )
    SUPPORTED_FILING_FORMS: list[str] = Field(
        default=["10-K", "10-Q", "10-K/A", "10-Q/A"],
        description="Supported statutory SEC filing types for document ingestion",
    )

    # Semantic Embeddings & Vector Indexing (Session 05)
    EMBEDDING_MODEL_NAME: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Pretrained sentence embedding model identifier",
    )
    EMBEDDING_DEVICE: str = Field(
        default="cpu",
        description="Compute device for embedding inference (cpu explicitly)",
    )
    EMBEDDING_BATCH_SIZE: int = Field(
        default=32,
        description="Batch size for generating embeddings",
    )
    EMBEDDING_INDEX_DIR: str = Field(
        default="datasets/indexes",
        description="Local directory for storing persistent vector index files",
    )
    EMBEDDING_BACKEND: str = Field(
        default="auto",
        description="Vector index backend ('auto', 'faiss', or 'numpy')",
    )
    EMBEDDING_SIMILARITY_THRESHOLD: float = Field(
        default=0.0,
        description="Minimum cosine similarity score threshold for semantic search results",
    )
    EMBEDDING_DIMENSION: int = Field(
        default=384,
        description="Expected vector dimension for the embedding model",
    )


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance.

    Returns:
        Settings: Initialized settings populated from environment and defaults.
    """
    return Settings()
