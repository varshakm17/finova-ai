"""Centralized logging system for Finova AI with automated secret redaction.

Provides console and file logging with standardized formatting and configurable
severity levels. Ensures logs directory is created automatically and redacts
sensitive credentials, access tokens, and contact identities from log streams.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from typing import Any

from config.settings import BASE_DIR, get_settings

DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

REDACT_PATTERNS = [
    # Redact email addresses
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
        "[REDACTED_EMAIL]",
    ),
    # Redact Authorization Bearer tokens
    (re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{16,}\b"), "Bearer [REDACTED_TOKEN]"),
    # Redact API keys and secrets in query strings or assignments
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{8,}['\"]?"
        ),
        r"\1=[REDACTED_SECRET]",
    ),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials and contact emails from record messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, repl in REDACT_PATTERNS:
                msg = pattern.sub(repl, msg)
            record.msg = msg

        # Also inspect and sanitize args if they contain strings
        if record.args:
            sanitized_args: list[Any] = []
            for arg in record.args:
                if isinstance(arg, str):
                    arg_str = arg
                    for pattern, repl in REDACT_PATTERNS:
                        arg_str = pattern.sub(repl, arg_str)
                    sanitized_args.append(arg_str)
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return True


def setup_logging(
    log_level: str | None = None,
    log_file_path: str | None = None,
) -> logging.Logger:
    """Configure centralized logging for both console and persistent file output.

    Args:
        log_level: Logging level string (e.g., 'DEBUG', 'INFO'). Defaults to settings.
        log_file_path: Relative or absolute path to the log file. Defaults to settings.

    Returns:
        logging.Logger: Root application logger for Finova AI.
    """
    settings = get_settings()

    level_name = (log_level or settings.LOG_LEVEL).upper()
    numeric_level = getattr(logging, level_name, logging.INFO)

    file_rel_path = log_file_path or settings.LOG_FILE_PATH
    resolved_file_path = BASE_DIR / file_rel_path
    resolved_file_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
    )

    redaction_filter = SensitiveDataFilter()

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        # Console Handler (unbuffered stdout/stderr for Docker & CLI)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(redaction_filter)
        root_logger.addHandler(console_handler)

        # Rotating File Handler (10MB max per file, up to 5 backups)
        file_handler = RotatingFileHandler(
            filename=str(resolved_file_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redaction_filter)
        root_logger.addHandler(file_handler)

    # Suppress overly chatty third-party loggers if not in DEBUG mode
    if numeric_level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("watchdog").setLevel(logging.WARNING)

    logger = logging.getLogger("finova")
    logger.info("Logging initialized at %s level -> %s", level_name, resolved_file_path)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Obtain a namespaced logger instance.

    Args:
        name: Name of the module or component.

    Returns:
        logging.Logger: Logger instance for the specified component.
    """
    return logging.getLogger(f"finova.{name}")
