"""Unit tests for runtime logging, observability, and secret redaction."""

from __future__ import annotations

import logging

from backend.utils.logger import SensitiveDataFilter, get_logger


def test_sensitive_data_filter_redacts_emails() -> None:
    """Verify contact emails are redacted from log messages."""
    filter_instance = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting with contact: user@example.com for SEC filings",
        args=(),
        exc_info=None,
    )

    filter_instance.filter(record)
    assert "[REDACTED_EMAIL]" in record.msg
    assert "user@example.com" not in record.msg


def test_sensitive_data_filter_redacts_tokens_and_keys() -> None:
    """Verify Bearer tokens and API keys are redacted from logs."""
    filter_instance = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Request header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and api_key=secret_key_12345678",
        args=(),
        exc_info=None,
    )

    filter_instance.filter(record)
    assert "[REDACTED_TOKEN]" in record.msg
    assert "[REDACTED_SECRET]" in record.msg
    assert "secret_key_12345678" not in record.msg


def test_get_logger_namespacing() -> None:
    """Verify get_logger returns namespaced logger."""
    log = get_logger("test_module")
    assert log.name == "finova.test_module"
