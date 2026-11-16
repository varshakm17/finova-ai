"""Comprehensive tests for ASGI request body size enforcement middleware."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from backend.api.middleware import RequestBodyLimitMiddleware


def create_test_app(max_bytes: int = 100) -> tuple[FastAPI, list[str]]:
    """Build a minimal test app with RequestBodyLimitMiddleware and an execution tracker."""
    app = FastAPI()
    executed_routes: list[str] = []

    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_bytes)

    @app.post("/test-endpoint")
    async def sample_post(request: Request):
        body = await request.body()
        executed_routes.append("sample_post")
        return {"status": "ok", "received_bytes": len(body)}

    @app.get("/test-get")
    async def sample_get():
        executed_routes.append("sample_get")
        return {"status": "ok"}

    return app, executed_routes


@pytest.mark.anyio
async def test_request_exactly_at_limit() -> None:
    """Verify request exactly at limit passes and executes route."""
    app, tracker = create_test_app(max_bytes=50)
    exact_payload = b"a" * 50

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/test-endpoint",
            content=exact_payload,
            headers={"Content-Length": "50"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["received_bytes"] == 50
    assert "sample_post" in tracker


@pytest.mark.anyio
async def test_request_one_byte_above_limit_content_length() -> None:
    """Verify request with Content-Length one byte above limit is rejected with 413 and never hits route."""
    app, tracker = create_test_app(max_bytes=50)
    oversized = b"a" * 51

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/test-endpoint",
            content=oversized,
            headers={"Content-Length": "51"},
        )

    assert resp.status_code == 413
    assert resp.json()["error"] is True
    assert "exceeds maximum permitted size" in resp.json()["message"]
    assert "sample_post" not in tracker


@pytest.mark.anyio
async def test_missing_content_length_within_limit() -> None:
    """Verify streamed request without Content-Length within limit passes."""
    app, tracker = create_test_app(max_bytes=100)

    async def stream_gen():
        yield b"chunk1-"
        yield b"chunk2"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/test-endpoint", content=stream_gen())

    assert resp.status_code == 200
    assert resp.json()["received_bytes"] == 13
    assert "sample_post" in tracker


@pytest.mark.anyio
async def test_missing_content_length_oversized_stream() -> None:
    """Verify streamed request without Content-Length exceeding limit is rejected with 413 and aborted."""
    app, tracker = create_test_app(max_bytes=50)

    async def stream_gen():
        yield b"x" * 30
        yield b"x" * 30  # Total 60 > 50

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/test-endpoint", content=stream_gen())

    assert resp.status_code == 413
    assert resp.json()["error"] is True
    assert "exceeded maximum permitted size" in resp.json()["message"]
    assert "sample_post" not in tracker


@pytest.mark.anyio
async def test_incorrect_content_length_spoofing() -> None:
    """Verify header claiming small size while body streams excess bytes is rejected."""
    app, tracker = create_test_app(max_bytes=50)

    # We manually simulate an ASGI stream where Content-Length was reported as 10,
    # but the actual receive delivers 60 bytes.
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test-endpoint",
        "query_string": b"",
        "headers": [(b"content-length", b"10")],
    }

    chunks = [b"a" * 30, b"b" * 30]
    idx = 0

    async def mock_receive():
        nonlocal idx
        if idx < len(chunks):
            data = chunks[idx]
            idx += 1
            return {
                "type": "http.request",
                "body": data,
                "more_body": idx < len(chunks),
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_messages = []

    async def mock_send(msg):
        sent_messages.append(msg)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=50)
    await middleware(scope, mock_receive, mock_send)

    # Verify HTTP 413 was sent
    assert len(sent_messages) >= 2
    assert sent_messages[0]["type"] == "http.response.start"
    assert sent_messages[0]["status"] == 413
    assert "sample_post" not in tracker


@pytest.mark.anyio
async def test_malformed_content_length_header() -> None:
    """Verify non-integer Content-Length header is rejected with 400 Bad Request."""
    app, tracker = create_test_app(max_bytes=100)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test-endpoint",
        "headers": [(b"content-length", b"invalid-not-int")],
    }
    sent_messages = []

    async def mock_receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def mock_send(msg):
        sent_messages.append(msg)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=100)
    await middleware(scope, mock_receive, mock_send)

    assert sent_messages[0]["status"] == 400
    assert "Invalid Content-Length" in str(sent_messages[1]["body"])
    assert "sample_post" not in tracker


@pytest.mark.anyio
async def test_negative_content_length_header() -> None:
    """Verify negative Content-Length header is rejected with 400 Bad Request."""
    app, tracker = create_test_app(max_bytes=100)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test-endpoint",
        "headers": [(b"content-length", b"-25")],
    }
    sent_messages = []

    async def mock_receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def mock_send(msg):
        sent_messages.append(msg)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=100)
    await middleware(scope, mock_receive, mock_send)

    assert sent_messages[0]["status"] == 400
    assert "negative length" in str(sent_messages[1]["body"])
    assert "sample_post" not in tracker


@pytest.mark.anyio
async def test_empty_body() -> None:
    """Verify empty body passes cleanly."""
    app, tracker = create_test_app(max_bytes=100)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/test-endpoint", content=b"")

    assert resp.status_code == 200
    assert resp.json()["received_bytes"] == 0
    assert "sample_post" in tracker


@pytest.mark.anyio
async def test_normal_json_request() -> None:
    """Verify standard JSON request within limits functions normally."""
    app, tracker = create_test_app(max_bytes=1000)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/test-endpoint", json={"ticker": "AAPL", "form": "10-K"}
        )

    assert resp.status_code == 200
    assert "sample_post" in tracker


@pytest.mark.anyio
async def test_get_request_bypasses_body_limit() -> None:
    """Verify GET requests without bodies proceed cleanly."""
    app, tracker = create_test_app(max_bytes=10)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/test-get")

    assert resp.status_code == 200
    assert "sample_get" in tracker
