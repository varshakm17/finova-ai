"""Finova AI — Backend Application Entrypoint & Lifecycle Management.

FastAPI application providing health diagnostics, financial intelligence APIs,
resilient CORS configuration, and multi-agent research coordination.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.data.sec_client import is_placeholder_user_agent
from backend.data.storage import Database
from backend.utils.logger import get_logger, setup_logging
from config.settings import Settings, get_settings

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup, diagnostics, and graceful shutdown."""
    settings = get_settings()
    setup_logging(log_level=settings.LOG_LEVEL, log_file_path=settings.LOG_FILE_PATH)

    logger.info("=" * 60)
    logger.info(
        "Starting %s v%s in [%s] mode",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )
    logger.info("Host Binding: http://%s:%s", settings.HOST, settings.PORT)
    logger.info("=" * 60)

    # 1. Database Startup Check
    try:
        db = Database()
        with db.connection() as conn:
            table_count = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
        logger.info(
            "[INIT] Database initialized successfully (SQLite WAL mode: %s, tables: %d)",
            settings.DATABASE_WAL_MODE,
            table_count,
        )
    except Exception as exc:
        logger.error("[INIT ERROR] Database initialization failed: %s", exc)

    # 2. SEC User-Agent Configuration Check
    if not settings.SEC_USER_AGENT or not settings.SEC_USER_AGENT.strip():
        logger.warning(
            "[CONFIG WARN] SEC_USER_AGENT is not configured. Live SEC EDGAR requests will be unavailable."
        )
    elif is_placeholder_user_agent(settings.SEC_USER_AGENT):
        logger.warning(
            "[CONFIG WARN] SEC_USER_AGENT contains an unconfigured placeholder identity. Set genuine contact in .env."
        )
    else:
        logger.info(
            "[INIT] SEC User-Agent verified: %s", settings.mask_sec_user_agent()
        )

    # 3. Optional Service Diagnostics
    logger.info(
        "[INIT] LLM Provider configured: '%s' (model: %s, base_url: %s)",
        settings.LLM_PROVIDER,
        settings.OLLAMA_MODEL,
        settings.OLLAMA_BASE_URL,
    )
    logger.info(
        "[INIT] Vector Index Backend: '%s' (embedding model: %s)",
        settings.EMBEDDING_BACKEND,
        settings.EMBEDDING_MODEL_NAME,
    )

    # 4. Production Security Checks
    prod_warnings = settings.validate_production_readiness()
    for warn in prod_warnings:
        logger.warning("[SECURITY AUDIT] %s", warn)

    yield

    logger.info("Shutting down %s cleanly...", settings.APP_NAME)


def create_application(custom_settings: Settings | None = None) -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Args:
        custom_settings: Optional Settings override for testing or custom configuration.

    Returns:
        FastAPI: Configured application ready for serving requests.
    """
    settings = custom_settings or get_settings()

    docs_url = "/docs" if settings.DOCS_ENABLED else None
    redoc_url = "/redoc" if settings.DOCS_ENABLED else None
    openapi_url = "/openapi.json" if settings.DOCS_ENABLED else None

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Finova AI is a multi-agent financial research and intelligence system "
            "designed to retrieve, analyze, verify, and report on corporate financial "
            "filings and quantitative metrics with evidence-backed citations."
        ),
        version=settings.APP_VERSION,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # CORS Configuration
    # -------------------------------------------------------------------------
    cors_origins = settings.get_cors_origins()
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS

    # Security rule: Never allow wildcard '*' with credentials=True
    if "*" in cors_origins and allow_credentials:
        logger.warning(
            "CORS wildcard origin '*' detected with allow_credentials=True. "
            "Enforcing allow_credentials=False for security compliance."
        )
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        max_age=600,
    )

    # -------------------------------------------------------------------------
    # Security Headers & Body Limit Middleware
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def security_and_limit_middleware(request: Request, call_next) -> Response:
        # Check payload size limit
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "error": True,
                    "status_code": 413,
                    "message": f"Request body exceeds maximum permitted size of {settings.MAX_REQUEST_BODY_BYTES} bytes.",
                    "path": request.url.path,
                },
            )

        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # -------------------------------------------------------------------------
    # Centralized Exception Handling
    # -------------------------------------------------------------------------
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        logger.warning(
            "HTTP %d error on %s: %s", exc.status_code, request.url.path, exc.detail
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "status_code": exc.status_code,
                "message": exc.detail,
                "path": request.url.path,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception on %s: %s", request.url.path, exc, exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "status_code": 500,
                "message": "An unexpected internal server error occurred.",
                "path": request.url.path,
            },
        )

    # -------------------------------------------------------------------------
    # Core Root & Direct Health Check Routes
    # -------------------------------------------------------------------------
    @app.get(
        "/",
        tags=["General"],
        summary="API Root Information",
        description="Returns basic system identity and links to documentation.",
    )
    def root_info() -> dict:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "description": "Multi-Agent Financial Research and Intelligence System",
            "documentation": "/docs" if settings.DOCS_ENABLED else "disabled",
            "health_check": "/health",
            "api_v1_prefix": settings.API_V1_PREFIX,
            "status": "operational",
        }

    @app.get(
        "/health",
        tags=["Diagnostics"],
        summary="Direct Health Check",
        description="Returns application health status, version, and environment.",
    )
    def direct_health_check() -> dict:
        return {
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        }

    # Mount versioned API routes
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    config = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
    )
