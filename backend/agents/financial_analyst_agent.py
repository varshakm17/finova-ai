"""Financial Analyst Agent for Finova AI Multi-Agent Orchestration.

Executes deterministic financial calculations using the corporate XBRL observations
stored in Finova AI. Guaranteed zero LLM arithmetic.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.base_agent import BaseFinovaAgent
from backend.agents.state import FinovaAgentState
from backend.finance.calculation_service import (
    ALL_CALCULATION_METRICS,
    CalculationService,
)
from backend.utils.logger import get_logger

logger = get_logger("financial_analyst_agent")

# Mapping of question keywords to canonical metric names
METRIC_KEYWORD_MAP: dict[str, list[str]] = {
    "revenue": ["revenue_growth"],
    "growth": ["revenue_growth"],
    "gross margin": ["gross_profit_margin"],
    "gross profit": ["gross_profit_margin"],
    "operating margin": ["operating_profit_margin"],
    "operating income": ["operating_profit_margin"],
    "net margin": ["net_profit_margin"],
    "net income": ["net_profit_margin"],
    "current ratio": ["current_ratio"],
    "liquidity": ["current_ratio"],
    "debt": ["debt_to_equity_ratio", "long_term_debt_to_equity"],
    "leverage": ["debt_to_equity_ratio"],
    "roe": ["return_on_equity"],
    "return on equity": ["return_on_equity"],
    "roa": ["return_on_assets"],
    "return on assets": ["return_on_assets"],
    "cash flow": ["operating_cash_flow_margin", "free_cash_flow"],
    "free cash flow": ["free_cash_flow"],
}


class FinancialAnalystAgent(BaseFinovaAgent):
    """Specialized agent executing deterministic financial ratio computations."""

    def __init__(self, calculation_service: CalculationService | None = None) -> None:
        super().__init__(
            agent_name="FinancialAnalystAgent",
            description="Computes deterministic financial metrics, margins, and ratios using structured XBRL data.",
        )
        self.calc_service = calculation_service or CalculationService()

    def identify_target_metrics(self, question: str) -> list[str]:
        """Identify which metrics to calculate based on query keywords."""
        lower_q = question.lower()
        matched_metrics: list[str] = []
        for kw, metric_list in METRIC_KEYWORD_MAP.items():
            if kw in lower_q:
                for m in metric_list:
                    if m not in matched_metrics:
                        matched_metrics.append(m)

        # If no specific metric keyword was detected, run all canonical metrics
        return matched_metrics if matched_metrics else ALL_CALCULATION_METRICS

    def extract_target_year(self, period_str: str | None) -> int | None:
        """Parse fiscal year from period string (e.g. 'FY2023' -> 2023)."""
        if not period_str:
            return None
        match = re.search(r"\b(20\d{2})\b", str(period_str))
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Compute deterministic financial metric receipts for target company."""
        ticker = state.get("company_ticker")
        question = state.get("user_question", "")
        period_str = state.get("reporting_period")
        target_year = self.extract_target_year(period_str)

        if not ticker:
            logger.warning("FinancialAnalystAgent: No target company ticker provided.")
            return {
                "calculation_results": [],
                "current_step": "financial_analyst_agent",
                "warnings": [
                    "No ticker available to perform deterministic financial calculations."
                ],
            }

        target_metrics = self.identify_target_metrics(question)
        logger.info(
            "FinancialAnalystAgent calculating metrics for %s (year=%s): %s",
            ticker,
            target_year,
            target_metrics[:4],
        )

        receipts_data: list[dict[str, Any]] = []
        warnings: list[str] = []

        try:
            summary = self.calc_service.calculate_company_metrics(
                ticker=ticker,
                start_year=target_year,
                end_year=target_year,
                metrics=target_metrics,
            )

            calc_list = getattr(
                summary, "calculations", getattr(summary, "receipts", [])
            )
            for receipt in calc_list:
                receipts_data.append(receipt.model_dump())

            if not receipts_data:
                msg = f"No deterministic financial observations found in DB for {ticker} (period: {period_str or 'all'})."
                warnings.append(msg)
                logger.info(msg)

        except Exception as exc:  # noqa: BLE001
            logger.error("FinancialAnalystAgent calculation failed: %s", exc)
            warnings.append(f"Financial calculations encountered an error: {exc}")

        return {
            "calculation_results": receipts_data,
            "current_step": "financial_analyst_agent",
            "warnings": warnings,
        }
