"""ASGI middleware for request payload size enforcement and security hardening.

Enforces configurable maximum request body size at the ASGI layer to prevent
memory exhaustion attacks via chunked, streamed, or spoofed HTTP requests.
"""

from __future__ import annotations

import json
from typing import Any, Callable


class PayloadTooLargeError(Exception):
    """Raised when request body bytes exceed the configured maximum threshold."""

    def __init__(self, message: str = "Request payload exceeds size limit.") -> None:
        super().__init__(message)
        self.message = message


class RequestBodyLimitMiddleware:
    """ASGI middleware enforcing strict request body size limits.

    Inspects Content-Length headers upfront, validates against malformed/negative values,
    and dynamically counts received bytes for chunked and streamed requests without
    buffering unlimited data in memory.
    """

    def __init__(
        self,
        app: Any,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        """Initialize middleware.

        Args:
            app: Downstream ASGI application.
            max_bytes: Maximum permitted request body size in bytes.
        """
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Process ASGI request scope."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cl_raw = headers.get(b"content-length")

        # 1. Upfront Content-Length header validation
        if cl_raw is not None:
            try:
                cl_str = cl_raw.decode("latin1").strip()
                cl_val = int(cl_str)
            except (ValueError, UnicodeDecodeError):
                await self._send_json_response(
                    send,
                    status_code=400,
                    message="Invalid Content-Length header: must be a valid non-negative integer.",
                    path=scope.get("path", ""),
                )
                return

            if cl_val < 0:
                await self._send_json_response(
                    send,
                    status_code=400,
                    message="Invalid Content-Length header: negative length is not permitted.",
                    path=scope.get("path", ""),
                )
                return

            if cl_val > self.max_bytes:
                await self._send_json_response(
                    send,
                    status_code=413,
                    message=f"Request body exceeds maximum permitted size of {self.max_bytes} bytes.",
                    path=scope.get("path", ""),
                )
                return

        # 2. Dynamic byte-counting stream wrapper (catches chunked & spoofed requests)
        received_bytes = 0
        response_started = False

        async def tracking_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def counting_receive() -> dict[str, Any]:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                received_bytes += len(chunk)
                if received_bytes > self.max_bytes:
                    raise PayloadTooLargeError(
                        f"Request body exceeded maximum permitted size of {self.max_bytes} bytes."
                    )
            return message

        try:
            await self.app(scope, counting_receive, tracking_send)
        except PayloadTooLargeError as exc:
            if not response_started:
                await self._send_json_response(
                    send,
                    status_code=413,
                    message=exc.message,
                    path=scope.get("path", ""),
                )
            return

    @staticmethod
    async def _send_json_response(
        send: Callable[[dict[str, Any]], Any],
        status_code: int,
        message: str,
        path: str = "",
    ) -> None:
        """Construct and emit a standardized JSON error response with security headers."""
        payload = json.dumps(
            {
                "error": True,
                "status_code": status_code,
                "message": message,
                "path": path,
            }
        ).encode("utf-8")

        response_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("ascii")),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"strict-origin-when-cross-origin"),
        ]

        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": response_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
            }
        )
