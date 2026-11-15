"""Deterministic financial calculation tools for Finova AI agents."""

from __future__ import annotations

from typing import Any

from backend.finance.calculation_service import (
    ALL_CALCULATION_METRICS,
    CalculationService,
)
from backend.utils.logger import get_logger

logger = get_logger("calculation_tools")


def compute_financial_metrics_tool(
    ticker: str,
    metrics: list[str] | None = None,
    year: int | None = None,
    calc_service: CalculationService | None = None,
) -> list[dict[str, Any]]:
    """Execute deterministic financial computations for a target company and period.

    Args:
        ticker: Stock ticker symbol (e.g. 'AAPL').
        metrics: Optional list of metrics to calculate.
        year: Optional fiscal year.
        calc_service: Optional service instance.

    Returns:
        List of serialized calculation receipt dictionaries.
    """
    service = calc_service or CalculationService()
    try:
        summary = service.calculate_company_metrics(
            ticker=ticker,
            start_year=year,
            end_year=year,
            metrics=metrics or ALL_CALCULATION_METRICS,
        )
        calcs = getattr(summary, "calculations", getattr(summary, "receipts", []))
        return [r.model_dump() for r in calcs]
    except Exception as exc:  # noqa: BLE001
        logger.error("compute_financial_metrics_tool failed: %s", exc)
        return []


def get_available_metrics_tool() -> list[str]:
    """Return all canonical financial metrics supported by the deterministic engine."""
    return list(ALL_CALCULATION_METRICS)
