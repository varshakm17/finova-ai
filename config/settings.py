"""Application configuration management using Pydantic Settings.

Loads configuration from environment variables and an optional .env file.
Provides safe development defaults for all fields so that missing optional configuration
never prevents the application from starting in development, while validating
strict production constraints.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
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

    # =========================================================================
    # 1. Core Application Metadata
    # =========================================================================
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

    # =========================================================================
    # 2. Backend Server & Security Configuration
    # =========================================================================
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
    CORS_ORIGINS: list[str] | str = Field(
        default=[
            "http://localhost:8501",
            "http://127.0.0.1:8501",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Allowed CORS origin URLs or comma-separated list of origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="Whether to permit credentials in CORS requests (must be False if wildcard * origin is used)",
    )
    DOCS_ENABLED: bool = Field(
        default=True,
        description="Enable FastAPI OpenAPI/Swagger and ReDoc documentation endpoints",
    )
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum permissible request body payload size in bytes (default: 10MB)",
    )

    # =========================================================================
    # 3. Frontend Connection Settings
    # =========================================================================
    BACKEND_API_URL: str | None = Field(
        default=None,
        description="Explicit backend URL for frontend client (e.g., http://backend:8000/api/v1 in Docker)",
    )

    # =========================================================================
    # 4. Logging Configuration
    # =========================================================================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging severity threshold (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    LOG_FILE_PATH: str = Field(
        default="logs/finova.log",
        description="Path relative to project root for application log output",
    )

    # =========================================================================
    # 5. Database Configuration (SQLite)
    # =========================================================================
    DATABASE_URL: str = Field(
        default="sqlite:///./finova.db",
        description="Database connection string (SQLite file path)",
    )
    DATABASE_WAL_MODE: bool = Field(
        default=True,
        description="Enable SQLite Write-Ahead Logging (WAL) mode for concurrency",
    )
    DATABASE_BUSY_TIMEOUT_MS: int = Field(
        default=30000,
        description="SQLite busy handler timeout in milliseconds before raising locked error",
    )

    # =========================================================================
    # 6. SEC EDGAR Integration & Fair-Access Settings
    # =========================================================================
    SEC_USER_AGENT: str = Field(
        default="",
        description=(
            "SEC EDGAR User-Agent header in the format: 'ApplicationName AdminContact@domain.com'. "
            "A valid email and identifier must be configured before making requests to SEC EDGAR."
        ),
    )
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

    # =========================================================================
    # 7. Semantic Embeddings & Persistent Vector Indexing
    # =========================================================================
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

    # =========================================================================
    # 8. BM25 Sparse Retrieval & Hybrid Search (RRF)
    # =========================================================================
    BM25_INDEX_DIR: str = Field(
        default="datasets/indexes/bm25",
        description="Local directory for storing persistent BM25 index and corpus files",
    )
    BM25_TOKENIZER_VERSION: str = Field(
        default="1.0.0",
        description="Semantic version of the financial BM25 tokenizer",
    )
    BM25_DEFAULT_TOP_K: int = Field(
        default=5,
        description="Default top-k results for BM25 lexical search",
    )
    BM25_K1: float = Field(
        default=1.5,
        description="BM25 term frequency saturation parameter k1",
    )
    BM25_B: float = Field(
        default=0.75,
        description="BM25 document length normalization parameter b",
    )
    HYBRID_RRF_CONSTANT: int = Field(
        default=60,
        description="Reciprocal Rank Fusion smoothing constant k (standard default 60)",
    )
    HYBRID_DENSE_CANDIDATES: int = Field(
        default=50,
        description="Over-fetch candidate count for dense semantic search in hybrid mode",
    )
    HYBRID_SPARSE_CANDIDATES: int = Field(
        default=50,
        description="Over-fetch candidate count for BM25 sparse search in hybrid mode",
    )
    HYBRID_DEFAULT_TOP_K: int = Field(
        default=5,
        description="Default top-k results for hybrid search",
    )

    # =========================================================================
    # 9. Retrieval Evaluation, Cross-Encoder Reranking & Evidence Quality
    # =========================================================================
    RERANKER_ENABLED: bool = Field(
        default=True,
        description="Enable optional cross-encoder reranking stage for hybrid retrieval candidates",
    )
    RERANKER_MODEL_NAME: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Pretrained cross-encoder model identifier for candidate reranking",
    )
    RERANKER_DEVICE: str = Field(
        default="cpu",
        description="Compute device for cross-encoder reranking inference (cpu explicitly)",
    )
    RERANKER_BATCH_SIZE: int = Field(
        default=16,
        description="Batch size for cross-encoder inference scoring",
    )
    RERANKER_CANDIDATE_COUNT: int = Field(
        default=25,
        description="Number of fused hybrid candidates to feed into the cross-encoder reranker",
    )
    RETRIEVAL_EVALUATION_DATASET: str = Field(
        default="datasets/evaluation/retrieval_queries.json",
        description="Default path to curated retrieval evaluation query dataset",
    )
    RETRIEVAL_EVALUATION_TOP_K: int = Field(
        default=5,
        description="Default top-k cutoff rank for standard IR evaluation metrics",
    )
    EVIDENCE_VALIDATION_ENABLED: bool = Field(
        default=True,
        description="Enable deterministic evidence provenance and duplicate validation",
    )

    # =========================================================================
    # 10. LLM Provider & Evidence-Grounded Financial RAG
    # =========================================================================
    LLM_PROVIDER: str = Field(
        default="ollama",
        description="Configured LLM provider ('ollama' or mock/custom)",
    )
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Base URL of local Ollama HTTP service",
    )
    OLLAMA_MODEL: str = Field(
        default="qwen2.5:3b",
        description="Model identifier for Ollama generation (e.g. qwen2.5:3b, llama3.2:3b)",
    )
    LLM_REQUEST_TIMEOUT: float = Field(
        default=60.0,
        description="Timeout in seconds for LLM generation HTTP requests",
    )
    LLM_TEMPERATURE: float = Field(
        default=0.1,
        description="Sampling temperature for deterministic, evidence-grounded generation",
    )
    LLM_MAX_TOKENS: int = Field(
        default=1024,
        description="Maximum generation output tokens",
    )
    LLM_CONTEXT_WINDOW: int = Field(
        default=4096,
        description="Maximum context window token capacity for prompt assembly",
    )
    RAG_DEFAULT_TOP_K: int = Field(
        default=5,
        description="Default number of evidence passages retrieved for RAG context",
    )
    RAG_MINIMUM_EVIDENCE: int = Field(
        default=1,
        description="Minimum number of valid evidence passages required to attempt answer generation",
    )
    RAG_MAX_CONTEXT_CHARACTERS: int = Field(
        default=12000,
        description="Maximum total character length of context text sent to LLM",
    )

    # =========================================================================
    # 11. Anti-Hallucination & Claim-Level Answer Verification
    # =========================================================================
    VERIFICATION_ENABLED: bool = Field(
        default=True,
        description="Enable post-generation claim-level answer verification",
    )
    VERIFICATION_NUMERIC_TOLERANCE_PCT: float = Field(
        default=1.0,
        description="Permitted relative percentage tolerance for numeric checks (e.g. 1.0 for 1% difference)",
    )
    VERIFICATION_STRICT_PERIODS: bool = Field(
        default=True,
        description="Enforce strict matching between claim period and evidence reporting period",
    )
    VERIFICATION_SEMANTIC_OVERLAP_THRESHOLD: float = Field(
        default=0.25,
        description="Token overlap threshold for deterministic lexical claim verification",
    )
    VERIFICATION_MAX_REGENERATION_ATTEMPTS: int = Field(
        default=1,
        description="Maximum regeneration attempts if an answer is contradicted or rejected",
    )
    VERIFICATION_ENABLE_REGENERATION: bool = Field(
        default=False,
        description="Enable automatic draft regeneration when answer verification fails",
    )
    VERIFICATION_VERSION: str = Field(
        default="0.1.0",
        description="Semantic version of the claim-level verification engine",
    )

    # =========================================================================
    # Field Validators
    # =========================================================================
    @field_validator("PORT")
    @classmethod
    def validate_port_range(cls, v: int) -> int:
        """Validate port is within valid TCP port range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got {v}")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Support comma-separated strings or string lists for CORS origins."""
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                return ["http://localhost:8501", "http://127.0.0.1:8501"]
            return [
                origin.strip() for origin in v_stripped.split(",") if origin.strip()
            ]
        if isinstance(v, (list, tuple)):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return ["http://localhost:8501", "http://127.0.0.1:8501"]

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_sqlite_url(cls, v: str) -> str:
        """Ensure database URL is a supported SQLite connection string."""
        if not v.startswith("sqlite:///"):
            raise ValueError(f"DATABASE_URL must start with 'sqlite:///', got '{v}'")
        return v

    # =========================================================================
    # Helper Methods
    # =========================================================================
    def get_cors_origins(self) -> list[str]:
        """Return CORS origins list with security guarantees."""
        origins = (
            self.CORS_ORIGINS
            if isinstance(self.CORS_ORIGINS, list)
            else [self.CORS_ORIGINS]
        )
        return origins

    def resolve_db_path(self) -> str:
        """Resolve database path from application settings to an absolute path or ':memory:'.

        Returns:
            str: Normalized absolute file path or ':memory:'.
        """
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            path_str = url[len("sqlite:///") :]
            if path_str == ":memory:":
                return ":memory:"

            # On Windows, handle URLs like sqlite:///C:/path
            if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
                path_str = path_str[1:]

            path = Path(path_str)
            if not path.is_absolute():
                path = (BASE_DIR / path).resolve()
            else:
                path = path.resolve()

            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)

        return str((BASE_DIR / "finova.db").resolve())

    def resolve_backend_api_url(self) -> str:
        """Resolve authoritative backend URL for API clients."""
        if self.BACKEND_API_URL and self.BACKEND_API_URL.strip():
            raw = self.BACKEND_API_URL.strip().rstrip("/")
            if not raw.startswith(("http://", "https://")):
                raw = f"http://{raw}"
            if not raw.endswith("/api/v1"):
                raw = f"{raw}{self.API_V1_PREFIX}"
            return raw

        host = self.HOST
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{self.PORT}{self.API_V1_PREFIX}"

    def mask_sec_user_agent(self) -> str:
        """Safely mask contact details in User-Agent header for public display."""
        ua = self.SEC_USER_AGENT
        if not ua or not ua.strip():
            return "[NOT CONFIGURED]"

        def _mask_email(match: re.Match) -> str:
            user, domain = match.group(1), match.group(2)
            masked_user = user[0] + "***" if user else "***"
            parts = domain.split(".")
            tld = parts[-1] if len(parts) > 1 else "com"
            return f"{masked_user}@{parts[0][0]}***.{tld}"

        return re.sub(
            r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
            _mask_email,
            ua,
        )

    def validate_production_readiness(self) -> list[str]:
        """Inspect configuration for security vulnerabilities before production launch."""
        warnings: list[str] = []
        if self.APP_ENV == "production":
            if self.DEBUG:
                warnings.append("DEBUG mode is enabled in production environment.")
            cors_list = self.get_cors_origins()
            if "*" in cors_list and self.CORS_ALLOW_CREDENTIALS:
                warnings.append(
                    "CORS wildcard '*' is combined with allow_credentials=True."
                )
            if not self.SEC_USER_AGENT or not self.SEC_USER_AGENT.strip():
                warnings.append("SEC_USER_AGENT is not configured.")
            else:
                from backend.data.sec_client import is_placeholder_user_agent

                if is_placeholder_user_agent(self.SEC_USER_AGENT):
                    warnings.append(
                        "SEC_USER_AGENT contains an unconfigured placeholder identity."
                    )
        return warnings


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance.

    Returns:
        Settings: Initialized settings populated from environment and defaults.
    """
    return Settings()
