"""API route definitions for Finova AI."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config.settings import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Schema for application health check response."""

    status: str = Field(..., description="Application operational status")
    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current deployment environment")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Application Health Check",
    description="Returns the operational status, application name, environment, and version.",
    tags=["Diagnostics"],
)
def get_health() -> HealthResponse:
    """Retrieve current service health and metadata."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
    )
