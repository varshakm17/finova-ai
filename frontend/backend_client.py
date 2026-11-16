"""Finova AI — Unified Frontend Backend Client & URL Resolver.

Resolves and normalizes backend API endpoints across:
- Local Windows development (127.0.0.1 / localhost)
- Docker Compose service-name networking (http://backend:8000/api/v1)
- Custom remote deployment URLs

Guarantees trailing-slash normalization, eliminates duplicate /api/v1 prefix segments,
and provides unified, resilient health checking and request execution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.utils.logger import get_logger
from config.settings import Settings, get_settings

logger = get_logger("backend_client")

DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = 8000
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_CONNECT_TIMEOUT = 3.0


@dataclass
class BackendEndpoints:
    """Resolved and normalized backend URL endpoints."""

    base_url: str  # Root URL (e.g. http://127.0.0.1:8000 or http://backend:8000)
    api_v1_url: str  # Versioned API root (e.g. http://127.0.0.1:8000/api/v1)
    health_url: (
        str  # Deep diagnostics endpoint (e.g. http://127.0.0.1:8000/api/v1/health)
    )
    root_health_url: (
        str  # Minimal root health endpoint (e.g. http://127.0.0.1:8000/health)
    )
    configured_from: str  # "environment", "settings", or "default"

    def endpoint(self, path: str) -> str:
        """Construct full URL for a specific endpoint path without duplicate /api/v1 segments."""
        clean_path = path.strip()
        if not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"

        if clean_path.startswith("/api/v1"):
            return f"{self.base_url}{clean_path}"
        return f"{self.api_v1_url}{clean_path}"


def resolve_backend_endpoints(
    custom_url: str | None = None,
    settings: Settings | None = None,
) -> BackendEndpoints:
    """Resolve and normalize backend API connection URLs.

    Precedence:
    1. custom_url parameter (if passed)
    2. BACKEND_API_URL environment variable
    3. settings.BACKEND_API_URL (if configured in .env)
    4. Derived from settings.HOST and settings.PORT (default local development)

    Args:
        custom_url: Optional explicit backend URL to resolve.
        settings: Optional Settings instance.

    Returns:
        BackendEndpoints: Normalized URLs with base, api_v1, and health endpoints.
    """
    cfg = settings or get_settings()

    raw_url: str | None = None
    source = "default"

    if custom_url and custom_url.strip():
        raw_url = custom_url.strip()
        source = "custom_parameter"
    elif os.environ.get("BACKEND_API_URL") and os.environ["BACKEND_API_URL"].strip():
        raw_url = os.environ["BACKEND_API_URL"].strip()
        source = "environment"
    elif cfg.BACKEND_API_URL and cfg.BACKEND_API_URL.strip():
        raw_url = cfg.BACKEND_API_URL.strip()
        source = "settings"
    else:
        host = cfg.HOST
        if host in ("0.0.0.0", "::"):
            host = DEFAULT_LOCAL_HOST
        port = cfg.PORT or DEFAULT_LOCAL_PORT
        raw_url = f"http://{host}:{port}{DEFAULT_API_PREFIX}"
        source = "default"

    # Normalize protocol & slashes
    clean_raw = raw_url.strip()
    if clean_raw.startswith("://") or clean_raw in ("http://", "https://"):
        raise ValueError(
            f"Invalid backend URL: '{raw_url}'. A valid hostname or IP address is required."
        )

    if not clean_raw.startswith(("http://", "https://")):
        url = f"http://{clean_raw.rstrip('/')}"
    else:
        url = clean_raw.rstrip("/")

    parsed = urlparse(url)
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(
            f"Invalid backend URL: '{raw_url}'. A valid hostname or IP address is required."
        )

    # Detect if URL already includes /api/v1 (or variant)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1"):
        base_path = path[: -len("/api/v1")]
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}".rstrip("/")
        api_v1_url = f"{base_url}/api/v1"
    else:
        base_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
        api_v1_url = f"{base_url}/api/v1"

    health_url = f"{api_v1_url}/health"
    root_health_url = f"{base_url}/health"

    return BackendEndpoints(
        base_url=base_url,
        api_v1_url=api_v1_url,
        health_url=health_url,
        root_health_url=root_health_url,
        configured_from=source,
    )


def check_backend_health(
    endpoints: BackendEndpoints | str,
    timeout: float = DEFAULT_CONNECT_TIMEOUT,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Inspect backend connectivity and return parsed diagnostics.

    Tries the versioned health diagnostics endpoint first (/api/v1/health),
    falling back to minimal root health endpoint (/health) if necessary.

    Args:
        endpoints: BackendEndpoints dataclass or raw URL string.
        timeout: Maximum seconds to wait before timing out.

    Returns:
        tuple[bool, dict | None, str | None]: (is_online, health_data, error_detail)
    """
    resolved = (
        endpoints
        if isinstance(endpoints, BackendEndpoints)
        else resolve_backend_endpoints(endpoints)
    )

    # 1. Try deep diagnostics endpoint
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(resolved.health_url)
            if resp.status_code == 200:
                data = resp.json()
                return True, data, None
            elif resp.status_code == 503:
                # Backend running but in degraded/unavailable state
                try:
                    return (
                        False,
                        resp.json(),
                        f"Service unavailable (HTTP 503): {resp.text}",
                    )
                except Exception:
                    return False, None, "Service unavailable (HTTP 503)"
            else:
                return (
                    False,
                    None,
                    f"Unexpected HTTP status {resp.status_code} from {resolved.health_url}",
                )
    except httpx.ConnectError:
        error_msg = (
            f"Connection refused to {resolved.base_url}. Ensure backend is running."
        )
    except httpx.TimeoutException:
        error_msg = (
            f"Connection timed out ({timeout}s) contacting {resolved.health_url}."
        )
    except Exception as exc:
        error_msg = f"Health check failed: {exc}"

    # 2. Fallback to root /health
    try:
        with httpx.Client(timeout=min(timeout, 1.5)) as client:
            fallback_resp = client.get(resolved.root_health_url)
            if fallback_resp.status_code == 200:
                return True, fallback_resp.json(), None
    except Exception:
        pass

    return False, None, error_msg
