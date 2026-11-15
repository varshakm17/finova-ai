"""Financial Calculation Service.

Coordinates data retrieval, period-alignment, input validation,
arithmetic computation, and receipt generation for corporate financial analysis.
"""

from typing import Any

from backend.data.company_service import CompanyService, normalize_ticker
from backend.data.data_normalizer import FinancialObservation
from backend.data.storage import Database
from backend.finance.calculation_engine import CalculationEngine
from backend.finance.calculation_models import (
    CalculationInputObservation,
    CalculationReceipt,
    CalculationSummaryResponse,
)
from backend.finance.period_validator import (
    find_opening_balance_observation,
    validate_units,
)
from backend.utils.logger import get_logger

logger = get_logger("calculation_service")

# List of all canonical metric identifiers supported by the calculation engine
ALL_CALCULATION_METRICS = [
    "revenue_growth",
    "gross_profit_margin",
    "operating_profit_margin",
    "net_profit_margin",
    "current_ratio",
    "debt_to_equity_ratio",
    "long_term_debt_to_equity",
    "return_on_assets",
    "return_on_equity",
    "operating_cash_flow_margin",
    "free_cash_flow",
]


class CalculationService:
    """Coordinates retrieval of financial facts and deterministic calculation of financial ratios."""

    def __init__(
        self,
        db: Database | None = None,
        company_service: CompanyService | None = None,
    ) -> None:
        self.db = db or Database()
        self.company_service = company_service or CompanyService()
        self.engine = CalculationEngine()

    def calculate_company_metrics(
        self,
        ticker: str,
        start_year: int | None = None,
        end_year: int | None = None,
        period_type: str = "annual",
        metrics: list[str] | None = None,
    ) -> CalculationSummaryResponse:
        """Execute deterministic financial calculations for a company across requested periods.

        Args:
            ticker: Stock ticker symbol (e.g. 'AAPL').
            start_year: Optional earliest fiscal year (inclusive).
            end_year: Optional latest fiscal year (inclusive).
            period_type: 'annual' or 'quarterly' (default: 'annual').
            metrics: Optional list of metric names. Defaults to ALL_CALCULATION_METRICS.

        Returns:
            CalculationSummaryResponse: Summary of calculated and unavailable metrics.
        """
        clean_ticker = normalize_ticker(ticker)
        company = self.db.get_company_by_ticker(clean_ticker)
        if not company:
            company = self.company_service.get_company_by_ticker(clean_ticker)

        if not company:
            raise ValueError(f"Company with ticker '{clean_ticker}' not found.")

        cik = company["cik"]
        company_name = company["name"]
        clean_period_type = period_type.lower().strip()

        # 1. Retrieve all stored observations for company
        all_obs = self.db.get_financial_observations(
            ticker_or_cik=clean_ticker,
            limit=5000,
        )

        # 2. Filter requested metrics
        target_metrics = [
            m.lower().strip() for m in (metrics or ALL_CALCULATION_METRICS)
        ]

        # 3. Partition observations into flow (Income/CashFlow) and instant (Balance Sheet)
        flow_obs = [
            o
            for o in all_obs
            if o.period_type == clean_period_type
            and (start_year is None or (o.fiscal_year and o.fiscal_year >= start_year))
            and (end_year is None or (o.fiscal_year and o.fiscal_year <= end_year))
        ]

        instant_obs = [o for o in all_obs if o.period_type == "instant"]

        # Group flow observations by period_end
        periods_dict: dict[str, dict[str, FinancialObservation]] = {}
        for o in flow_obs:
            if o.period_end not in periods_dict:
                periods_dict[o.period_end] = {}
            periods_dict[o.period_end][o.metric_name] = o

        # Also group instant observations by period_end for balance sheet-only metrics (Current Ratio, Debt-to-Equity)
        instant_by_date: dict[str, dict[str, FinancialObservation]] = {}
        for o in instant_obs:
            if (
                start_year is None or (o.fiscal_year and o.fiscal_year >= start_year)
            ) and (end_year is None or (o.fiscal_year and o.fiscal_year <= end_year)):
                if o.period_end not in instant_by_date:
                    instant_by_date[o.period_end] = {}
                instant_by_date[o.period_end][o.metric_name] = o

        # Combine all unique target reporting dates
        all_period_ends = sorted(
            set(periods_dict.keys()) | set(instant_by_date.keys()),
            reverse=True,
        )

        receipts: list[CalculationReceipt] = []

        # 4. Perform calculations across each reporting period
        for period_end in all_period_ends:
            period_flow = periods_dict.get(period_end, {})
            period_instant = instant_by_date.get(period_end, {})

            # Determine representative fiscal year and period
            rep_obs = next(iter(period_flow.values()), None) or next(
                iter(period_instant.values()), None
            )
            fiscal_year = rep_obs.fiscal_year if rep_obs else None
            fiscal_period = rep_obs.fiscal_period if rep_obs else None
            period_start = rep_obs.period_start if rep_obs else None

            # A. Revenue Growth
            if "revenue_growth" in target_metrics:
                receipts.append(
                    self._compute_revenue_growth(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        all_obs,
                    )
                )

            # B. Gross Profit Margin
            if "gross_profit_margin" in target_metrics:
                receipts.append(
                    self._compute_margin(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        num_metric="Gross Profit",
                        metric_key="gross_profit_margin",
                        formula_name="Gross Profit Margin",
                        formula_expr="(Gross Profit / Revenue) * 100",
                        calc_func=self.engine.calculate_gross_profit_margin,
                    )
                )

            # C. Operating Profit Margin
            if "operating_profit_margin" in target_metrics:
                receipts.append(
                    self._compute_margin(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        num_metric="Operating Income",
                        metric_key="operating_profit_margin",
                        formula_name="Operating Profit Margin",
                        formula_expr="(Operating Income / Revenue) * 100",
                        calc_func=self.engine.calculate_operating_profit_margin,
                    )
                )

            # D. Net Profit Margin
            if "net_profit_margin" in target_metrics:
                receipts.append(
                    self._compute_margin(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        num_metric="Net Income",
                        metric_key="net_profit_margin",
                        formula_name="Net Profit Margin",
                        formula_expr="(Net Income / Revenue) * 100",
                        calc_func=self.engine.calculate_net_profit_margin,
                    )
                )

            # E. Current Ratio
            if "current_ratio" in target_metrics:
                receipts.append(
                    self._compute_current_ratio(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_instant,
                    )
                )

            # F1. Debt-to-Equity Ratio (Total Debt)
            if "debt_to_equity_ratio" in target_metrics:
                receipts.append(
                    self._compute_debt_to_equity(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_instant,
                    )
                )

            # F2. Long-Term Debt-to-Equity Ratio
            if "long_term_debt_to_equity" in target_metrics:
                receipts.append(
                    self._compute_long_term_debt_to_equity(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_instant,
                    )
                )

            # G. Return on Assets (ROA)
            if "return_on_assets" in target_metrics:
                receipts.append(
                    self._compute_return_on_assets(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        instant_obs,
                    )
                )

            # H. Return on Equity (ROE)
            if "return_on_equity" in target_metrics:
                receipts.append(
                    self._compute_return_on_equity(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        instant_obs,
                    )
                )

            # I. Operating Cash Flow Margin
            if "operating_cash_flow_margin" in target_metrics:
                receipts.append(
                    self._compute_margin(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                        num_metric="Operating Cash Flow",
                        metric_key="operating_cash_flow_margin",
                        formula_name="Operating Cash Flow Margin",
                        formula_expr="(Operating Cash Flow / Revenue) * 100",
                        calc_func=self.engine.calculate_operating_cash_flow_margin,
                    )
                )

            # J. Free Cash Flow
            if "free_cash_flow" in target_metrics:
                receipts.append(
                    self._compute_free_cash_flow(
                        clean_ticker,
                        cik,
                        company_name,
                        clean_period_type,
                        period_start,
                        period_end,
                        fiscal_year,
                        fiscal_period,
                        period_flow,
                    )
                )

        # 5. Persist calculated receipts into SQLite
        raw_receipts_data = [
            {
                "calculation_id": r.calculation_id,
                "cik": r.cik,
                "ticker": r.ticker,
                "company_name": r.company_name,
                "metric_name": r.metric_name,
                "calculated_value": r.calculated_value,
                "unit": r.unit,
                "period_type": r.period_type,
                "period_start": r.period_start or "",
                "period_end": r.period_end,
                "fiscal_year": r.fiscal_year,
                "fiscal_period": r.fiscal_period,
                "formula_name": r.formula_name,
                "formula_expression": r.formula_expression,
                "calculation_status": r.status,
                "unavailable_reason": r.unavailable_reason,
                "input_observations": [inp.model_dump() for inp in r.inputs],
                "warnings": r.warnings,
                "calculated_at": r.calculated_at,
            }
            for r in receipts
        ]
        self.db.save_financial_calculations(raw_receipts_data)

        # Summarize counts
        total_calc = sum(1 for r in receipts if r.status == "calculated")
        total_unavail = sum(1 for r in receipts if r.status == "unavailable")
        total_invalid = sum(1 for r in receipts if r.status == "invalid_inputs")

        logger.info(
            "Calculations completed for %s (%s): %d calculated, %d unavailable, %d invalid",
            clean_ticker,
            clean_period_type,
            total_calc,
            total_unavail,
            total_invalid,
        )

        return CalculationSummaryResponse(
            ticker=clean_ticker,
            cik=cik,
            company_name=company_name,
            period_type=clean_period_type,
            total_calculated=total_calc,
            total_unavailable=total_unavail,
            total_invalid=total_invalid,
            calculations=receipts,
        )

    # -------------------------------------------------------------------------
    # Metric Calculation Helpers
    # -------------------------------------------------------------------------

    def _make_input_record(
        self, obs: FinancialObservation, note: str | None = None
    ) -> CalculationInputObservation:
        """Create a provenance record for an observation used as a formula input."""
        return CalculationInputObservation(
            metric_name=obs.metric_name,
            value=obs.numeric_value,
            unit=obs.unit,
            period_start=obs.period_start,
            period_end=obs.period_end,
            period_type=obs.period_type,
            filing_type=obs.filing_type,
            accession_number=obs.accession_number,
            source_url=obs.source_url,
            normalization_note=note,
        )

    def _compute_revenue_growth(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_flow: dict[str, FinancialObservation],
        all_obs: list[FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Revenue Growth against the prior equivalent reporting period."""
        calc_id = f"{cik}_revenue_growth_{period_type}_{period_end}"
        current_rev = period_flow.get("Revenue")

        if not current_rev:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="revenue_growth",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Revenue Growth",
                formula_expression="((Current Revenue - Previous Revenue) / Previous Revenue) * 100",
                status="unavailable",
                unavailable_reason="Current period Revenue observation is not available.",
            )

        # Locate previous period revenue
        prior_rev: FinancialObservation | None = None
        candidates = [
            o
            for o in all_obs
            if o.metric_name == "Revenue"
            and o.period_type == period_type
            and o.period_end < period_end
        ]

        if candidates:
            # Sort by period_end descending to find the immediately preceding period
            candidates.sort(key=lambda x: x.period_end, reverse=True)
            prior_rev = candidates[0]

        if not prior_rev:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="revenue_growth",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Revenue Growth",
                formula_expression="((Current Revenue - Previous Revenue) / Previous Revenue) * 100",
                status="unavailable",
                unavailable_reason="Previous period Revenue observation not found for comparison.",
                inputs=[self._make_input_record(current_rev)],
            )

        # Validate unit compatibility
        valid_units, unit_err = validate_units(
            [current_rev, prior_rev], expected_unit="USD"
        )
        if not valid_units:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="revenue_growth",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Revenue Growth",
                formula_expression="((Current Revenue - Previous Revenue) / Previous Revenue) * 100",
                status="invalid_inputs",
                unavailable_reason=unit_err,
                inputs=[
                    self._make_input_record(current_rev),
                    self._make_input_record(prior_rev),
                ],
            )

        try:
            val = self.engine.calculate_revenue_growth(
                current_rev.numeric_value, prior_rev.numeric_value
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="revenue_growth",
                calculated_value=round(val, 4),
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Revenue Growth",
                formula_expression="((Current Revenue - Previous Revenue) / Previous Revenue) * 100",
                status="calculated",
                inputs=[
                    self._make_input_record(current_rev),
                    self._make_input_record(prior_rev),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="revenue_growth",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Revenue Growth",
                formula_expression="((Current Revenue - Previous Revenue) / Previous Revenue) * 100",
                status="invalid_inputs",
                unavailable_reason="Previous period Revenue is zero; percentage growth undefined.",
                inputs=[
                    self._make_input_record(current_rev),
                    self._make_input_record(prior_rev),
                ],
            )

    def _compute_margin(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_flow: dict[str, FinancialObservation],
        num_metric: str,
        metric_key: str,
        formula_name: str,
        formula_expr: str,
        calc_func: Any,
    ) -> CalculationReceipt:
        """Compute flow-based margin metric relative to Revenue."""
        calc_id = f"{cik}_{metric_key}_{period_type}_{period_end}"
        num_obs = period_flow.get(num_metric)
        rev_obs = period_flow.get("Revenue")

        missing = []
        if not num_obs:
            missing.append(num_metric)
        if not rev_obs:
            missing.append("Revenue")

        if missing:
            inputs = [self._make_input_record(o) for o in [num_obs, rev_obs] if o]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name=metric_key,
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name=formula_name,
                formula_expression=formula_expr,
                status="unavailable",
                unavailable_reason=f"Missing required input observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        # Validate units
        valid_units, unit_err = validate_units([num_obs, rev_obs], expected_unit="USD")
        if not valid_units:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name=metric_key,
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name=formula_name,
                formula_expression=formula_expr,
                status="invalid_inputs",
                unavailable_reason=unit_err,
                inputs=[
                    self._make_input_record(num_obs),
                    self._make_input_record(rev_obs),
                ],
            )

        try:
            val = calc_func(num_obs.numeric_value, rev_obs.numeric_value)
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name=metric_key,
                calculated_value=round(val, 4),
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name=formula_name,
                formula_expression=formula_expr,
                status="calculated",
                inputs=[
                    self._make_input_record(num_obs),
                    self._make_input_record(rev_obs),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name=metric_key,
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name=formula_name,
                formula_expression=formula_expr,
                status="invalid_inputs",
                unavailable_reason="Revenue is zero; margin calculation undefined.",
                inputs=[
                    self._make_input_record(num_obs),
                    self._make_input_record(rev_obs),
                ],
            )

    def _compute_current_ratio(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_instant: dict[str, FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Current Ratio from balance sheet assets and liabilities."""
        calc_id = f"{cik}_current_ratio_{period_type}_{period_end}"
        ca_obs = period_instant.get("Current Assets")
        cl_obs = period_instant.get("Current Liabilities")

        missing = []
        if not ca_obs:
            missing.append("Current Assets")
        if not cl_obs:
            missing.append("Current Liabilities")

        if missing:
            inputs = [self._make_input_record(o) for o in [ca_obs, cl_obs] if o]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="current_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Current Ratio",
                formula_expression="Current Assets / Current Liabilities",
                status="unavailable",
                unavailable_reason=f"Missing balance sheet observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        valid_units, unit_err = validate_units([ca_obs, cl_obs], expected_unit="USD")
        if not valid_units:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="current_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Current Ratio",
                formula_expression="Current Assets / Current Liabilities",
                status="invalid_inputs",
                unavailable_reason=unit_err,
                inputs=[
                    self._make_input_record(ca_obs),
                    self._make_input_record(cl_obs),
                ],
            )

        try:
            val = self.engine.calculate_current_ratio(
                ca_obs.numeric_value, cl_obs.numeric_value
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="current_ratio",
                calculated_value=round(val, 4),
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Current Ratio",
                formula_expression="Current Assets / Current Liabilities",
                status="calculated",
                inputs=[
                    self._make_input_record(ca_obs),
                    self._make_input_record(cl_obs),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="current_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Current Ratio",
                formula_expression="Current Assets / Current Liabilities",
                status="invalid_inputs",
                unavailable_reason="Current Liabilities is zero; current ratio undefined.",
                inputs=[
                    self._make_input_record(ca_obs),
                    self._make_input_record(cl_obs),
                ],
            )

    def _compute_debt_to_equity(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_instant: dict[str, FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Debt-to-Equity Ratio using Total Debt (explicitly marked unavailable if Total Debt absent)."""
        calc_id = f"{cik}_debt_to_equity_ratio_{period_type}_{period_end}"
        td_obs = period_instant.get("Total Debt")
        eq_obs = period_instant.get("Stockholders' Equity")

        if not td_obs:
            inputs = [self._make_input_record(eq_obs)] if eq_obs else []
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="debt_to_equity_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Debt to Equity Ratio",
                formula_expression="Total Debt / Stockholders' Equity",
                status="unavailable",
                unavailable_reason="Total Debt observation is not reported in statutory XBRL facts. Use long_term_debt_to_equity for available Long-Term Debt.",
                inputs=inputs,
            )

        if not eq_obs:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="debt_to_equity_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Debt to Equity Ratio",
                formula_expression="Total Debt / Stockholders' Equity",
                status="unavailable",
                unavailable_reason="Stockholders' Equity observation is not available.",
                inputs=[self._make_input_record(td_obs)],
            )

        try:
            val = self.engine.calculate_debt_to_equity(
                td_obs.numeric_value, eq_obs.numeric_value
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="debt_to_equity_ratio",
                calculated_value=round(val, 4),
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Debt to Equity Ratio",
                formula_expression="Total Debt / Stockholders' Equity",
                status="calculated",
                inputs=[
                    self._make_input_record(td_obs),
                    self._make_input_record(eq_obs),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="debt_to_equity_ratio",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Debt to Equity Ratio",
                formula_expression="Total Debt / Stockholders' Equity",
                status="invalid_inputs",
                unavailable_reason="Stockholders' Equity is zero; debt-to-equity ratio undefined.",
                inputs=[
                    self._make_input_record(td_obs),
                    self._make_input_record(eq_obs),
                ],
            )

    def _compute_long_term_debt_to_equity(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_instant: dict[str, FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Long-Term Debt to Equity Ratio using explicitly labeled Long-Term Debt."""
        calc_id = f"{cik}_long_term_debt_to_equity_{period_type}_{period_end}"
        ltd_obs = period_instant.get("Long-Term Debt")
        eq_obs = period_instant.get("Stockholders' Equity")

        missing = []
        if not ltd_obs:
            missing.append("Long-Term Debt")
        if not eq_obs:
            missing.append("Stockholders' Equity")

        if missing:
            inputs = [self._make_input_record(o) for o in [ltd_obs, eq_obs] if o]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="long_term_debt_to_equity",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Long-Term Debt to Equity Ratio",
                formula_expression="Long-Term Debt / Stockholders' Equity",
                status="unavailable",
                unavailable_reason=f"Missing balance sheet observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        try:
            val = self.engine.calculate_long_term_debt_to_equity(
                ltd_obs.numeric_value, eq_obs.numeric_value
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="long_term_debt_to_equity",
                calculated_value=round(val, 4),
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Long-Term Debt to Equity Ratio",
                formula_expression="Long-Term Debt / Stockholders' Equity",
                status="calculated",
                inputs=[
                    self._make_input_record(ltd_obs),
                    self._make_input_record(eq_obs),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="long_term_debt_to_equity",
                calculated_value=None,
                unit="ratio",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Long-Term Debt to Equity Ratio",
                formula_expression="Long-Term Debt / Stockholders' Equity",
                status="invalid_inputs",
                unavailable_reason="Stockholders' Equity is zero; long-term debt-to-equity ratio undefined.",
                inputs=[
                    self._make_input_record(ltd_obs),
                    self._make_input_record(eq_obs),
                ],
            )

    def _compute_return_on_assets(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_flow: dict[str, FinancialObservation],
        instant_obs: list[FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Return on Assets (ROA) using Average Total Assets."""
        calc_id = f"{cik}_return_on_assets_{period_type}_{period_end}"
        ni_obs = period_flow.get("Net Income")

        # Closing Total Assets at period_end
        closing_assets_obs = next(
            (
                o
                for o in instant_obs
                if o.metric_name == "Total Assets" and o.period_end == period_end
            ),
            None,
        )

        missing = []
        if not ni_obs:
            missing.append("Net Income")
        if not closing_assets_obs:
            missing.append("Closing Total Assets")

        if missing:
            inputs = [
                self._make_input_record(o) for o in [ni_obs, closing_assets_obs] if o
            ]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_assets",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Assets",
                formula_expression="(Net Income / ((Opening Total Assets + Closing Total Assets) / 2)) * 100",
                status="unavailable",
                unavailable_reason=f"Missing required input observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        # Locate Opening Total Assets
        opening_assets_obs = find_opening_balance_observation(
            metric_name="Total Assets",
            closing_period_start=period_start,
            candidate_observations=instant_obs,
        )

        if not opening_assets_obs:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_assets",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Assets",
                formula_expression="(Net Income / ((Opening Total Assets + Closing Total Assets) / 2)) * 100",
                status="unavailable",
                unavailable_reason=(
                    f"Opening balance sheet observation for Total Assets at {period_start} is missing; "
                    "cannot compute average total assets without fabricating data."
                ),
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(closing_assets_obs, note="Closing Balance"),
                ],
            )

        try:
            val = self.engine.calculate_return_on_assets(
                net_income=ni_obs.numeric_value,
                opening_total_assets=opening_assets_obs.numeric_value,
                closing_total_assets=closing_assets_obs.numeric_value,
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_assets",
                calculated_value=round(val, 4),
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Assets",
                formula_expression="(Net Income / ((Opening Total Assets + Closing Total Assets) / 2)) * 100",
                status="calculated",
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(opening_assets_obs, note="Opening Balance"),
                    self._make_input_record(closing_assets_obs, note="Closing Balance"),
                ],
            )
        except (ZeroDivisionError, ValueError) as exc:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_assets",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Assets",
                formula_expression="(Net Income / ((Opening Total Assets + Closing Total Assets) / 2)) * 100",
                status="invalid_inputs",
                unavailable_reason=f"Invalid assets value: {exc}",
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(opening_assets_obs, note="Opening Balance"),
                    self._make_input_record(closing_assets_obs, note="Closing Balance"),
                ],
            )

    def _compute_return_on_equity(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_flow: dict[str, FinancialObservation],
        instant_obs: list[FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Return on Equity (ROE) using Average Stockholders' Equity."""
        calc_id = f"{cik}_return_on_equity_{period_type}_{period_end}"
        ni_obs = period_flow.get("Net Income")

        closing_eq_obs = next(
            (
                o
                for o in instant_obs
                if o.metric_name == "Stockholders' Equity"
                and o.period_end == period_end
            ),
            None,
        )

        missing = []
        if not ni_obs:
            missing.append("Net Income")
        if not closing_eq_obs:
            missing.append("Closing Stockholders' Equity")

        if missing:
            inputs = [self._make_input_record(o) for o in [ni_obs, closing_eq_obs] if o]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_equity",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Equity",
                formula_expression="(Net Income / ((Opening Equity + Closing Equity) / 2)) * 100",
                status="unavailable",
                unavailable_reason=f"Missing required input observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        opening_eq_obs = find_opening_balance_observation(
            metric_name="Stockholders' Equity",
            closing_period_start=period_start,
            candidate_observations=instant_obs,
        )

        if not opening_eq_obs:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_equity",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Equity",
                formula_expression="(Net Income / ((Opening Equity + Closing Equity) / 2)) * 100",
                status="unavailable",
                unavailable_reason=(
                    f"Opening balance sheet observation for Stockholders' Equity at {period_start} is missing; "
                    "cannot compute average stockholders' equity without fabricating data."
                ),
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(closing_eq_obs, note="Closing Balance"),
                ],
            )

        try:
            val = self.engine.calculate_return_on_equity(
                net_income=ni_obs.numeric_value,
                opening_equity=opening_eq_obs.numeric_value,
                closing_equity=closing_eq_obs.numeric_value,
            )
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_equity",
                calculated_value=round(val, 4),
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Equity",
                formula_expression="(Net Income / ((Opening Equity + Closing Equity) / 2)) * 100",
                status="calculated",
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(opening_eq_obs, note="Opening Balance"),
                    self._make_input_record(closing_eq_obs, note="Closing Balance"),
                ],
            )
        except ZeroDivisionError:
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="return_on_equity",
                calculated_value=None,
                unit="percentage",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Return on Equity",
                formula_expression="(Net Income / ((Opening Equity + Closing Equity) / 2)) * 100",
                status="invalid_inputs",
                unavailable_reason="Average Stockholders' Equity is zero; ROE undefined.",
                inputs=[
                    self._make_input_record(ni_obs),
                    self._make_input_record(opening_eq_obs, note="Opening Balance"),
                    self._make_input_record(closing_eq_obs, note="Closing Balance"),
                ],
            )

    def _compute_free_cash_flow(
        self,
        ticker: str,
        cik: str,
        company_name: str,
        period_type: str,
        period_start: str | None,
        period_end: str,
        fiscal_year: int | None,
        fiscal_period: str | None,
        period_flow: dict[str, FinancialObservation],
    ) -> CalculationReceipt:
        """Compute Free Cash Flow with explicit CapEx sign normalization."""
        calc_id = f"{cik}_free_cash_flow_{period_type}_{period_end}"
        ocf_obs = period_flow.get("Operating Cash Flow")
        capex_obs = period_flow.get("Capital Expenditures")

        missing = []
        if not ocf_obs:
            missing.append("Operating Cash Flow")
        if not capex_obs:
            missing.append("Capital Expenditures")

        if missing:
            inputs = [self._make_input_record(o) for o in [ocf_obs, capex_obs] if o]
            return CalculationReceipt(
                calculation_id=calc_id,
                ticker=ticker,
                cik=cik,
                company_name=company_name,
                metric_name="free_cash_flow",
                calculated_value=None,
                unit="USD",
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                formula_name="Free Cash Flow",
                formula_expression="Operating Cash Flow - Normalized CapEx",
                status="unavailable",
                unavailable_reason=f"Missing cash flow observation(s): {', '.join(missing)}.",
                inputs=inputs,
            )

        fcf, norm_capex, explanation = self.engine.calculate_free_cash_flow(
            ocf_obs.numeric_value, capex_obs.numeric_value
        )

        return CalculationReceipt(
            calculation_id=calc_id,
            ticker=ticker,
            cik=cik,
            company_name=company_name,
            metric_name="free_cash_flow",
            calculated_value=round(fcf, 2),
            unit="USD",
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            formula_name="Free Cash Flow",
            formula_expression="Operating Cash Flow - Normalized CapEx",
            status="calculated",
            inputs=[
                self._make_input_record(ocf_obs),
                self._make_input_record(
                    capex_obs,
                    note=f"Reported value: {capex_obs.numeric_value:g}, normalized to positive outflow {norm_capex:g}",
                ),
            ],
            warnings=[explanation],
        )
