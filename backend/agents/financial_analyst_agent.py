"""Financial Analyst Agent for Finova AI Multi-Agent Orchestration.

Executes deterministic financial calculations using the corporate XBRL observations
stored in Finova AI. Guaranteed zero LLM arithmetic.
Computes multi-period financial trends, percentage changes, and comparisons.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.agent_models import (
    FinancialAnalysisResult,
    FinancialTrend,
    MetricComparison,
)
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
    """Specialized agent executing deterministic financial computations and multi-period trend analysis."""

    def __init__(self, calculation_service: CalculationService | None = None) -> None:
        super().__init__(
            agent_name="FinancialAnalystAgent",
            description="Computes deterministic financial metrics, margins, ratios, and multi-period trends.",
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
        match = re.search(r"(?:^|\D)(20\d{2})\b", str(period_str))
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def extract_target_years(self, state: FinovaAgentState) -> list[int]:
        """Extract all target fiscal years from state (plan, period, question)."""
        years: set[int] = set()

        # Check research plan if available
        plan = state.get("research_plan")
        if plan:
            periods = []
            if isinstance(plan, dict):
                periods = plan.get("target_periods", [])
            elif hasattr(plan, "target_periods"):
                periods = plan.target_periods

            for p in periods:
                found = re.findall(r"(?:^|\D)(20\d{2})\b", str(p))
                for y in found:
                    years.add(int(y))

        # Check reporting_period in state
        period_str = state.get("reporting_period")
        if period_str:
            found = re.findall(r"(?:^|\D)(20\d{2})\b", str(period_str))
            for y in found:
                years.add(int(y))

        # Check user question
        question = state.get("user_question", "")
        if question:
            found = re.findall(r"(?:^|\D)(20\d{2})\b", str(question))
            for y in found:
                years.add(int(y))

        return sorted(list(years))

    def generate_trend_interpretation(
        self,
        metric_name: str,
        direction: str,
        percentage_change: float | None,
        absolute_change: float,
        unit: str,
    ) -> str:
        """Deterministic financial interpretation of observed longitudinal metric movement."""
        pct_text = (
            f" ({percentage_change:+.1f}%)" if percentage_change is not None else ""
        )
        abs_text = f"{absolute_change:+.2f} {unit}"

        if direction == "FLAT":
            return f"{metric_name} remained essentially flat over the observed period ({abs_text})."

        profitability_metrics = {
            "gross_profit_margin",
            "operating_profit_margin",
            "net_profit_margin",
            "operating_cash_flow_margin",
            "return_on_assets",
            "return_on_equity",
        }
        leverage_metrics = {"debt_to_equity_ratio", "long_term_debt_to_equity"}
        liquidity_metrics = {"current_ratio"}

        if direction == "UPWARD":
            if metric_name in profitability_metrics:
                return f"Profitability and operational efficiency expanded{pct_text} across the comparative periods."
            if metric_name in leverage_metrics:
                return f"Financial leverage increased{pct_text}, reflecting greater reliance on debt financing."
            if metric_name in liquidity_metrics:
                return f"Short-term liquidity position strengthened{pct_text}, improving working capital headroom."
            if metric_name == "revenue_growth":
                return f"Revenue growth accelerated{pct_text} over comparative fiscal periods."
            return f"{metric_name} increased by {abs_text}{pct_text} over the observed timeframe."

        if direction == "DOWNWARD":
            if metric_name in profitability_metrics:
                return (
                    f"Profitability margins experienced downward compression{pct_text}."
                )
            if metric_name in leverage_metrics:
                return f"Financial leverage decreased{pct_text}, indicating debt reduction and balance sheet de-leveraging."
            if metric_name in liquidity_metrics:
                return f"Short-term liquidity tightened{pct_text}, reducing working capital buffers."
            if metric_name == "revenue_growth":
                return f"Top-line revenue expansion decelerated{pct_text}."
            return f"{metric_name} declined by {abs_text}{pct_text} over the observed timeframe."

        return f"{metric_name} demonstrated mixed volatility across periods (net shift: {abs_text}{pct_text})."

    def compute_trends(
        self,
        receipts: list[dict[str, Any]],
    ) -> tuple[list[FinancialTrend], list[MetricComparison]]:
        """Compute deterministic multi-period trends and period-over-period comparisons.

        Guaranteed zero LLM arithmetic.
        """
        # Group receipts by metric_name
        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in receipts:
            if r.get("status") != "calculated" or r.get("calculated_value") is None:
                continue
            m = r.get("metric_name")
            if not m:
                continue
            grouped.setdefault(m, []).append(r)

        trends: list[FinancialTrend] = []
        comparisons: list[MetricComparison] = []

        for metric_name, m_receipts in grouped.items():
            # Sort by fiscal year and fiscal period
            valid_receipts = [r for r in m_receipts if r.get("fiscal_year") is not None]
            if not valid_receipts:
                continue

            sorted_receipts = sorted(
                valid_receipts,
                key=lambda x: (
                    x.get("fiscal_year", 0),
                    x.get("fiscal_period", "FY"),
                ),
            )

            periods = [
                f"FY{r.get('fiscal_year')}"
                if r.get("fiscal_period") in ("FY", None)
                else f"FY{r.get('fiscal_year')}-{r.get('fiscal_period')}"
                for r in sorted_receipts
            ]
            values = [float(r["calculated_value"]) for r in sorted_receipts]
            unit = sorted_receipts[0].get("unit", "")
            receipt_ids = [
                str(r.get("calculation_id") or r.get("id", "")) for r in sorted_receipts
            ]

            # Generate period-over-period comparisons
            for i in range(len(values) - 1):
                b_p = periods[i]
                b_v = values[i]
                c_p = periods[i + 1]
                c_v = values[i + 1]
                abs_delta = round(c_v - b_v, 4)
                pct_delta = (
                    round(((c_v - b_v) / abs(b_v)) * 100.0, 2)
                    if abs(b_v) > 1e-6
                    else None
                )

                comparisons.append(
                    MetricComparison(
                        metric_name=metric_name,
                        base_period=b_p,
                        base_value=round(b_v, 4),
                        comparison_period=c_p,
                        comparison_value=round(c_v, 4),
                        absolute_delta=abs_delta,
                        percentage_delta=pct_delta,
                        unit=unit,
                    )
                )

            # Generate multi-period trend if >= 2 periods
            if len(values) >= 2:
                base_v = values[0]
                final_v = values[-1]
                abs_change = round(final_v - base_v, 4)
                pct_change = (
                    round(((final_v - base_v) / abs(base_v)) * 100.0, 2)
                    if abs(base_v) > 1e-6
                    else None
                )

                # Direction analysis
                deltas = [values[j + 1] - values[j] for j in range(len(values) - 1)]
                if all(abs(d) < 0.0001 for d in deltas) or abs(abs_change) < 0.0001:
                    direction = "FLAT"
                elif all(d > 0.0001 for d in deltas):
                    direction = "UPWARD"
                elif all(d < -0.0001 for d in deltas):
                    direction = "DOWNWARD"
                else:
                    # If net shift is significant in one direction, or mixed
                    direction = "MIXED"

                interpretation = self.generate_trend_interpretation(
                    metric_name=metric_name,
                    direction=direction,
                    percentage_change=pct_change,
                    absolute_change=abs_change,
                    unit=unit,
                )

                trends.append(
                    FinancialTrend(
                        metric_name=metric_name,
                        periods=periods,
                        values=[round(v, 4) for v in values],
                        unit=unit,
                        direction=direction,
                        absolute_change=abs_change,
                        percentage_change=pct_change,
                        supporting_receipt_ids=receipt_ids,
                        interpretation_notes=interpretation,
                    )
                )

        return trends, comparisons

    def execute(self, state: FinovaAgentState) -> dict[str, Any]:
        """Compute deterministic financial metric receipts and multi-period trends for target company."""
        ticker = state.get("company_ticker")
        question = state.get("user_question", "")
        intent = state.get("intent", "")
        workflow = state.get("workflow_type", "")

        if not ticker:
            logger.warning("FinancialAnalystAgent: No target company ticker provided.")
            return {
                "calculation_results": [],
                "financial_analysis": None,
                "current_step": "financial_analyst_agent",
                "warnings": [
                    "No ticker available to perform deterministic financial calculations."
                ],
            }

        target_metrics = self.identify_target_metrics(question)

        # Check target years
        extracted_years = self.extract_target_years(state)
        is_report_workflow = (
            intent == "report_generation"
            or workflow == "financial_research_report"
            or "report" in question.lower()
            or "trend" in question.lower()
        )

        start_year: int | None = None
        end_year: int | None = None

        if extracted_years:
            min_year = min(extracted_years)
            max_year = max(extracted_years)
            if min_year != max_year:
                start_year = min_year
                end_year = max_year
            elif is_report_workflow:
                # If report workflow with single year, pull comparative prior year if available
                start_year = max(2015, min_year - 2)
                end_year = max_year
            else:
                # Targeted single year query
                start_year = min_year
                end_year = max_year
        elif not is_report_workflow:
            # Fallback to single year extraction from period_str if present
            period_str = state.get("reporting_period")
            single_year = self.extract_target_year(period_str)
            if single_year:
                start_year = single_year
                end_year = single_year

        logger.info(
            "FinancialAnalystAgent calculating metrics for %s (years: %s to %s): %s",
            ticker,
            start_year,
            end_year,
            target_metrics[:4],
        )

        receipts_data: list[dict[str, Any]] = []
        warnings: list[str] = []
        company_name = ticker

        try:
            summary = self.calc_service.calculate_company_metrics(
                ticker=ticker,
                start_year=start_year,
                end_year=end_year,
                metrics=target_metrics,
            )

            calc_list = getattr(
                summary, "calculations", getattr(summary, "receipts", [])
            )
            for receipt in calc_list:
                receipts_data.append(receipt.model_dump())

            if calc_list and hasattr(calc_list[0], "company_name"):
                company_name = calc_list[0].company_name

            if not receipts_data:
                msg = f"No deterministic financial observations found in DB for {ticker} (years: {start_year}-{end_year})."
                warnings.append(msg)
                logger.info(msg)

        except Exception as exc:  # noqa: BLE001
            logger.error("FinancialAnalystAgent calculation failed: %s", exc)
            warnings.append(f"Financial calculations encountered an error: {exc}")

        # Compute multi-period trends and comparisons
        trends, comparisons = self.compute_trends(receipts_data)

        # Build periods analyzed list
        periods_analyzed = sorted(
            list(
                {
                    f"FY{r.get('fiscal_year')}"
                    for r in receipts_data
                    if r.get("fiscal_year") is not None
                }
            )
        )

        analysis_result = FinancialAnalysisResult(
            ticker=ticker,
            company_name=company_name,
            period_type="annual",
            periods_analyzed=periods_analyzed,
            trends=trends,
            comparisons=comparisons,
            calculation_receipts=receipts_data,
            missing_metrics=[],
            warnings=warnings,
        )

        return {
            "calculation_results": receipts_data,
            "financial_analysis": analysis_result.model_dump(),
            "current_step": "financial_analyst_agent",
            "warnings": warnings,
        }
