"""Finova AI — Backend Application Entrypoint.

FastAPI application providing health checks, financial intelligence APIs,
and multi-agent research coordination.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router
from backend.utils.logger import get_logger, setup_logging
from config.settings import get_settings

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle events."""
    settings = get_settings()
    setup_logging(log_level=settings.LOG_LEVEL, log_file_path=settings.LOG_FILE_PATH)
    logger.info(
        "Starting %s v%s in [%s] mode",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_application() -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Returns:
        FastAPI: Configured application ready for serving requests.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Finova AI is a multi-agent financial research and intelligence system "
            "designed to retrieve, analyze, verify, and report on corporate financial "
            "filings and quantitative metrics with evidence-backed citations."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (CORS) Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Centralized Exception Handling
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
        logger.error("Unhandled exception on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "status_code": 500,
                "message": "An unexpected internal server error occurred.",
                "path": request.url.path,
            },
        )

    # Root informational route
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
            "documentation": "/docs",
            "health_check": "/health",
            "status": "operational",
        }

    # Mount /health directly at root as required
    @app.get(
        "/health",
        tags=["Diagnostics"],
        summary="Direct Health Check",
        description="Returns application health status, version, and environment.",
    )
    def health_check() -> dict:
        return {
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        }

    # Include versioned API router
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
